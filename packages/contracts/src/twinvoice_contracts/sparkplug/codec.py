"""Sparkplug B 3.0 payload encoding/decoding using plain Python dicts, plus topic helpers."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, NotRequired, TypedDict

from twinvoice_contracts.sparkplug import sparkplug_b_pb2 as pb

NAMESPACE = "spBv1.0"
BDSEQ_METRIC = "bdSeq"
REBIRTH_METRIC = "Node Control/Rebirth"

type Scalar = bool | int | float | str


class DataType(StrEnum):
    INT8 = "Int8"
    INT16 = "Int16"
    INT32 = "Int32"
    INT64 = "Int64"
    UINT8 = "UInt8"
    UINT16 = "UInt16"
    UINT32 = "UInt32"
    UINT64 = "UInt64"
    FLOAT = "Float"
    DOUBLE = "Double"
    BOOLEAN = "Boolean"
    STRING = "String"
    DATETIME = "DateTime"
    TEXT = "Text"
    UUID = "UUID"


@dataclass(frozen=True, slots=True)
class _TypeSpec:
    code: int
    field: str
    bits: int | None = None  # integer width; None for non-integers
    signed: bool = False


_SPECS: dict[DataType, _TypeSpec] = {
    DataType.INT8: _TypeSpec(1, "int_value", 8, True),
    DataType.INT16: _TypeSpec(2, "int_value", 16, True),
    DataType.INT32: _TypeSpec(3, "int_value", 32, True),
    DataType.INT64: _TypeSpec(4, "long_value", 64, True),
    DataType.UINT8: _TypeSpec(5, "int_value", 8),
    DataType.UINT16: _TypeSpec(6, "int_value", 16),
    DataType.UINT32: _TypeSpec(7, "int_value", 32),
    DataType.UINT64: _TypeSpec(8, "long_value", 64),
    DataType.FLOAT: _TypeSpec(9, "float_value"),
    DataType.DOUBLE: _TypeSpec(10, "double_value"),
    DataType.BOOLEAN: _TypeSpec(11, "boolean_value"),
    DataType.STRING: _TypeSpec(12, "string_value"),
    DataType.DATETIME: _TypeSpec(13, "long_value", 64),
    DataType.TEXT: _TypeSpec(14, "string_value"),
    DataType.UUID: _TypeSpec(15, "string_value"),
}
_BY_CODE: dict[int, DataType] = {spec.code: dt for dt, spec in _SPECS.items()}


class MetricDict(TypedDict):
    name: str
    datatype: DataType | str
    value: NotRequired[Scalar | None]
    timestamp: NotRequired[int | None]
    is_null: NotRequired[bool]
    properties: NotRequired[Mapping[str, Scalar | None]]


class PayloadDict(TypedDict):
    timestamp: int | None
    seq: int | None
    metrics: list[MetricDict]


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def _to_wire(dt: DataType, value: Scalar) -> Scalar:
    spec = _SPECS[dt]
    if spec.bits is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{dt} requires an int, got {value!r}")
        lo, hi = (
            (-(2 ** (spec.bits - 1)), 2 ** (spec.bits - 1)) if spec.signed else (0, 2**spec.bits)
        )
        if not lo <= value < hi:
            raise ValueError(f"{value} out of range for {dt}")
        return value + 2**spec.bits if value < 0 else value
    if spec.field in ("float_value", "double_value"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{dt} requires a number, got {value!r}")
        return float(value)
    if spec.field == "boolean_value":
        if not isinstance(value, bool):
            raise ValueError(f"{dt} requires a bool, got {value!r}")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{dt} requires a str, got {value!r}")
    return value


def _from_wire(dt: DataType, raw: Scalar) -> Scalar:
    spec = _SPECS[dt]
    if spec.bits is not None and spec.signed:
        # Mask first: some encoders sign-extend narrow ints to 32 bits.
        v = int(raw) & (2**spec.bits - 1)
        return v - 2**spec.bits if v >= 2 ** (spec.bits - 1) else v
    return raw


def _infer_property_type(value: Scalar | None) -> DataType:
    if value is None or isinstance(value, str):
        return DataType.STRING
    if isinstance(value, bool):
        return DataType.BOOLEAN
    if isinstance(value, int):
        return DataType.INT32 if -(2**31) <= value < 2**31 else DataType.INT64
    return DataType.DOUBLE


def _set_value(target: Any, dt: DataType, value: Scalar | None, is_null: bool) -> None:
    if is_null or value is None:
        target.is_null = True
        return
    setattr(target, _SPECS[dt].field, _to_wire(dt, value))


def _read_value(source: Any, type_code: int) -> tuple[DataType, Scalar | None, bool]:
    dt = _BY_CODE.get(type_code)
    if dt is None:
        raise ValueError(f"unsupported Sparkplug datatype code {type_code}")
    if source.is_null:
        return dt, None, True
    field = source.WhichOneof("value")
    if field is None:
        return dt, None, True
    return dt, _from_wire(dt, getattr(source, field)), False


def _encode_metric(target: pb.Payload.Metric, metric: MetricDict) -> None:
    dt = DataType(metric["datatype"])
    target.name = metric["name"]
    target.datatype = _SPECS[dt].code
    if (ts := metric.get("timestamp")) is not None:
        target.timestamp = ts
    _set_value(target, dt, metric.get("value"), metric.get("is_null", False))
    for key, pvalue in (metric.get("properties") or {}).items():
        target.properties.keys.append(key)
        prop = target.properties.values.add()
        pdt = _infer_property_type(pvalue)
        prop.type = _SPECS[pdt].code
        _set_value(prop, pdt, pvalue, pvalue is None)


def _decode_metric(source: pb.Payload.Metric) -> MetricDict:
    dt, value, is_null = _read_value(source, source.datatype)
    properties: dict[str, Scalar | None] = {}
    if source.HasField("properties"):
        for key, prop in zip(source.properties.keys, source.properties.values, strict=True):
            properties[key] = _read_value(prop, prop.type)[1]
    return MetricDict(
        name=source.name,
        datatype=dt,
        value=value,
        timestamp=source.timestamp if source.HasField("timestamp") else None,
        is_null=is_null,
        properties=properties,
    )


def encode_payload(
    metrics: Iterable[MetricDict], *, timestamp: int | None = None, seq: int | None = None
) -> bytes:
    payload = pb.Payload()
    payload.timestamp = now_ms() if timestamp is None else timestamp
    if seq is not None:
        if not 0 <= seq <= 255:
            raise ValueError(f"seq must be 0..255, got {seq}")
        payload.seq = seq
    for metric in metrics:
        _encode_metric(payload.metrics.add(), metric)
    return payload.SerializeToString()


def decode_payload(data: bytes) -> PayloadDict:
    payload = pb.Payload()
    payload.ParseFromString(data)
    return PayloadDict(
        timestamp=payload.timestamp if payload.HasField("timestamp") else None,
        seq=payload.seq if payload.HasField("seq") else None,
        metrics=[_decode_metric(m) for m in payload.metrics],
    )


def _bdseq_metric(bd_seq: int, timestamp: int) -> MetricDict:
    return MetricDict(name=BDSEQ_METRIC, datatype=DataType.INT64, value=bd_seq, timestamp=timestamp)


def nbirth(
    bd_seq: int, metrics: Sequence[MetricDict] = (), *, timestamp: int | None = None
) -> bytes:
    ts = now_ms() if timestamp is None else timestamp
    control = MetricDict(name=REBIRTH_METRIC, datatype=DataType.BOOLEAN, value=False, timestamp=ts)
    return encode_payload([_bdseq_metric(bd_seq, ts), control, *metrics], timestamp=ts, seq=0)


def ndeath(bd_seq: int, *, timestamp: int | None = None) -> bytes:
    ts = now_ms() if timestamp is None else timestamp
    return encode_payload([_bdseq_metric(bd_seq, ts)], timestamp=ts)


def dbirth(metrics: Sequence[MetricDict], seq: int, *, timestamp: int | None = None) -> bytes:
    return encode_payload(metrics, timestamp=timestamp, seq=seq)


def ddata(metrics: Sequence[MetricDict], seq: int, *, timestamp: int | None = None) -> bytes:
    return encode_payload(metrics, timestamp=timestamp, seq=seq)


def ddeath(seq: int, *, timestamp: int | None = None) -> bytes:
    return encode_payload([], timestamp=timestamp, seq=seq)


class MessageType(StrEnum):
    NBIRTH = "NBIRTH"
    NDEATH = "NDEATH"
    NDATA = "NDATA"
    NCMD = "NCMD"
    DBIRTH = "DBIRTH"
    DDEATH = "DDEATH"
    DDATA = "DDATA"
    DCMD = "DCMD"

    @property
    def is_device(self) -> bool:
        return self.value.startswith("D")


@dataclass(frozen=True, slots=True)
class Topic:
    group_id: str
    message_type: MessageType
    edge_node_id: str
    device_id: str | None = None

    def __str__(self) -> str:
        return build_topic(self.group_id, self.message_type, self.edge_node_id, self.device_id)


def _check_id(label: str, value: str) -> None:
    if not value or any(c in value for c in "/+#"):
        raise ValueError(f"invalid Sparkplug {label}: {value!r}")


def build_topic(
    group_id: str,
    message_type: MessageType | str,
    edge_node_id: str,
    device_id: str | None = None,
) -> str:
    mt = MessageType(message_type)
    _check_id("group_id", group_id)
    _check_id("edge_node_id", edge_node_id)
    if mt.is_device != (device_id is not None):
        raise ValueError(f"{mt} {'requires' if mt.is_device else 'forbids'} a device_id")
    parts = [NAMESPACE, group_id, mt.value, edge_node_id]
    if device_id is not None:
        _check_id("device_id", device_id)
        parts.append(device_id)
    return "/".join(parts)


def parse_topic(topic: str) -> Topic:
    parts = topic.split("/")
    if len(parts) not in (4, 5) or parts[0] != NAMESPACE:
        raise ValueError(f"not a Sparkplug B topic: {topic!r}")
    try:
        mt = MessageType(parts[2])
    except ValueError as exc:
        raise ValueError(f"unknown Sparkplug message type in {topic!r}") from exc
    device = parts[4] if len(parts) == 5 else None
    if mt.is_device != (device is not None) or not all(parts[1:]):
        raise ValueError(f"malformed Sparkplug topic: {topic!r}")
    return Topic(parts[1], mt, parts[3], device)
