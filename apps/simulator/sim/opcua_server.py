"""OPC UA mirror of live metrics: Objects/{plant}/{line}/{asset}/{metric}, anonymous access."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from asyncua import Server, ua

from sim.catalog import Catalog
from sim.live import AssetSnapshot
from sim.sensors import MetricDef

log = logging.getLogger(__name__)

ENDPOINT = "opc.tcp://0.0.0.0:4840/twinvoice/"
NAMESPACE_URI = "urn:twinvoice:simulator"

_VARIANT_TYPES = {
    "Double": (ua.VariantType.Double, 0.0),
    "Int64": (ua.VariantType.Int64, 0),
    "String": (ua.VariantType.String, ""),
}
_GOOD = ua.StatusCode(ua.StatusCodes.Good)
_NO_DATA = ua.StatusCode(ua.StatusCodes.BadNoCommunication)


class OpcUaMirror:
    def __init__(
        self, catalog: Catalog, metric_defs: dict[str, list[MetricDef]], endpoint: str = ENDPOINT
    ) -> None:
        self.catalog = catalog
        self.metric_defs = metric_defs
        self.endpoint = endpoint
        self._server = Server()
        self._nodes: dict[tuple[str, str], tuple[ua.NodeId, ua.VariantType]] = {}
        self._last: dict[tuple[str, str], float | int | str] = {}

    async def start(self) -> None:
        server = self._server
        await server.init()
        server.set_endpoint(self.endpoint)
        server.set_server_name("TwinVoice Simulator")
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        ns = await server.register_namespace(NAMESPACE_URI)
        plant = self.catalog.fleet.plant.code
        plant_node = await server.nodes.objects.add_folder(
            ua.NodeId(plant, ns), ua.QualifiedName(plant, ns)
        )
        for line in self.catalog.fleet.lines:
            line_path = f"{plant}/{line.code}"
            line_node = await plant_node.add_folder(
                ua.NodeId(line_path, ns), ua.QualifiedName(line.code, ns)
            )
            for asset in line.assets:
                asset_path = f"{line_path}/{asset.code}"
                asset_node = await line_node.add_object(
                    ua.NodeId(asset_path, ns), ua.QualifiedName(asset.code, ns)
                )
                for d in self.metric_defs[asset.code]:
                    variant_type, initial = _VARIANT_TYPES[d.datatype]
                    node = await asset_node.add_variable(
                        ua.NodeId(f"{asset_path}/{d.name}", ns),
                        ua.QualifiedName(d.name, ns),
                        initial,
                        variant_type,
                    )
                    if d.unit:
                        await node.write_attribute(
                            ua.AttributeIds.Description,
                            ua.DataValue(
                                ua.Variant(ua.LocalizedText(d.unit), ua.VariantType.LocalizedText)
                            ),
                        )
                    self._nodes[(asset.code, d.name)] = (node.nodeid, variant_type)
                    self._last[(asset.code, d.name)] = initial
        await server.start()
        log.info("OPC UA server listening on %s", self.endpoint)

    async def publish(self, snapshots: list[AssetSnapshot]) -> None:
        now = datetime.now(UTC)
        for snap in snapshots:
            for name, value in snap.values.items():
                key = (snap.code, name)
                nodeid, variant_type = self._nodes[key]
                if value is None:
                    status, value = _NO_DATA, self._last[key]
                else:
                    status = _GOOD
                    self._last[key] = value
                data = ua.DataValue(
                    ua.Variant(value, variant_type),
                    StatusCode=status,
                    SourceTimestamp=now,
                    ServerTimestamp=now,
                )
                await self._server.write_attribute_value(nodeid, data)

    async def stop(self) -> None:
        await self._server.stop()
