"""Modbus TCP mirror: one device id per asset, read-only holding registers (map in the catalog)."""

from __future__ import annotations

import logging
import math
import struct
from functools import partial

from pymodbus.constants import ExcCodes
from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from sim.catalog import MODBUS_GOOD_REGISTER, MODBUS_REJECT_REGISTER, MODBUS_STATE_REGISTER, Catalog
from sim.live import AssetSnapshot
from sim.machines import State

log = logging.getLogger(__name__)

PORT = 5020
STATE_CODES = {
    State.RUNNING.value: 0,
    State.IDLE.value: 1,
    State.DOWN.value: 2,
    State.MAINTENANCE.value: 3,
    State.UNKNOWN.value: 4,
}


def float32_words(value: float | None) -> tuple[int, int]:
    """IEEE-754 float32, big-endian, high word first; missing values are NaN."""
    raw = struct.pack(">f", math.nan if value is None else value)
    return int.from_bytes(raw[:2], "big"), int.from_bytes(raw[2:], "big")


def uint32_words(value: int) -> tuple[int, int]:
    value &= 0xFFFFFFFF
    return value >> 16, value & 0xFFFF


class ModbusMirror:
    def __init__(self, catalog: Catalog, host: str = "0.0.0.0", port: int = PORT) -> None:
        self.address = (host, port)
        self.units: dict[str, int] = {}
        self.registers: dict[str, dict[str, int]] = {}
        self.images: dict[int, list[int]] = {}
        devices = []
        for unit, asset in enumerate(catalog.assets, start=1):
            registers = catalog.modbus_registers(asset.code)
            size = max(registers.values()) + 2
            self.units[asset.code] = unit
            self.registers[asset.code] = registers
            self.images[unit] = [0] * size
            self.images[unit][MODBUS_STATE_REGISTER] = STATE_CODES[State.UNKNOWN.value]
            block = SimData(0, count=size, values=0, datatype=DataType.REGISTERS, readonly=True)
            devices.append(SimDevice(unit, simdata=[block], action=partial(self._serve, unit)))
        self._devices = devices
        self._server: ModbusTcpServer | None = None

    async def _serve(
        self,
        unit: int,
        _function_code: int,
        _start_address: int,
        _address: int,
        _count: int,
        registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> ExcCodes | None:
        if set_values is not None:
            return ExcCodes.ILLEGAL_FUNCTION
        image = self.images[unit]
        registers[: len(image)] = image
        return None

    def encode(self, snap: AssetSnapshot) -> None:
        image = self.images[self.units[snap.code]]
        image[MODBUS_STATE_REGISTER] = STATE_CODES.get(str(snap.values["state"]), 4)
        for name, base in (
            ("good_count", MODBUS_GOOD_REGISTER),
            ("reject_count", MODBUS_REJECT_REGISTER),
        ):
            image[base : base + 2] = uint32_words(int(snap.values[name] or 0))
        for name, address in self.registers[snap.code].items():
            if name in ("state", "good_count", "reject_count"):
                continue
            value = snap.values.get(name)
            image[address : address + 2] = float32_words(
                float(value) if isinstance(value, int | float) else None
            )

    async def start(self) -> None:
        self._server = ModbusTcpServer(self._devices, address=self.address)
        await self._server.serve_forever(background=True)
        log.info("Modbus TCP server listening on %s:%s", *self.address)

    async def publish(self, snapshots: list[AssetSnapshot]) -> None:
        for snap in snapshots:
            self.encode(snap)

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
