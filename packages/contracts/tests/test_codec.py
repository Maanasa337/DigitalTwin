import pytest

from twinvoice_contracts.sparkplug import (
    BDSEQ_METRIC,
    REBIRTH_METRIC,
    DataType,
    MessageType,
    MetricDict,
    Topic,
    build_topic,
    dbirth,
    ddata,
    ddeath,
    decode_payload,
    encode_payload,
    nbirth,
    ndeath,
    parse_topic,
)
from twinvoice_contracts.sparkplug import sparkplug_b_pb2 as pb

TS = 1_758_000_000_123

ROUND_TRIP_CASES: list[tuple[DataType, object]] = [
    (DataType.DOUBLE, 3.141592653589793),
    (DataType.DOUBLE, -1e-300),
    (DataType.FLOAT, 1.5),
    (DataType.INT32, -2_147_483_648),
    (DataType.INT32, 2_147_483_647),
    (DataType.INT64, -9_223_372_036_854_775_808),
    (DataType.INT64, 42),
    (DataType.UINT32, 4_294_967_295),
    (DataType.UINT64, 18_446_744_073_709_551_615),
    (DataType.BOOLEAN, True),
    (DataType.BOOLEAN, False),
    (DataType.STRING, "RUNNING"),
    (DataType.STRING, ""),
]


@pytest.mark.parametrize(("datatype", "value"), ROUND_TRIP_CASES)
def test_scalar_round_trip(datatype: DataType, value: object) -> None:
    metric = MetricDict(name="m", datatype=datatype, value=value, timestamp=TS)  # type: ignore[typeddict-item]
    decoded = decode_payload(encode_payload([metric], timestamp=TS, seq=7))
    assert decoded["timestamp"] == TS
    assert decoded["seq"] == 7
    (out,) = decoded["metrics"]
    assert out["name"] == "m"
    assert out["datatype"] == datatype
    assert out["value"] == value
    assert type(out["value"]) is type(value)
    assert out["timestamp"] == TS
    assert out["is_null"] is False
    assert out["properties"] == {}


def test_plain_string_datatype_accepted() -> None:
    (out,) = decode_payload(encode_payload([{"name": "x", "datatype": "Int64", "value": -5}]))[
        "metrics"
    ]
    assert out["datatype"] == "Int64"
    assert out["value"] == -5


@pytest.mark.parametrize("datatype", [DataType.DOUBLE, DataType.INT64, DataType.STRING])
def test_null_metric_round_trip(datatype: DataType) -> None:
    metric = MetricDict(name="spindle.temp", datatype=datatype, value=None, timestamp=TS)
    (out,) = decode_payload(encode_payload([metric]))["metrics"]
    assert out["is_null"] is True
    assert out["value"] is None
    assert out["datatype"] == datatype


def test_is_null_flag_overrides_value() -> None:
    metric = MetricDict(name="a", datatype=DataType.DOUBLE, value=1.0, is_null=True)
    (out,) = decode_payload(encode_payload([metric]))["metrics"]
    assert out["is_null"] is True
    assert out["value"] is None


def test_properties_round_trip() -> None:
    props = {"engUnit": "mm/s", "Quality": 192, "big": 2**40, "flag": True, "gain": 0.25, "n": None}
    metric = MetricDict(
        name="spindle.vib_rms", datatype=DataType.DOUBLE, value=None, properties=props
    )
    (out,) = decode_payload(encode_payload([metric]))["metrics"]
    assert out["properties"] == props
    assert out["is_null"] is True


def test_property_types_on_wire() -> None:
    metric = MetricDict(
        name="x", datatype=DataType.DOUBLE, value=1.0, properties={"engUnit": "A", "Quality": 0}
    )
    raw = pb.Payload.FromString(encode_payload([metric]))
    ps = raw.metrics[0].properties
    types = dict(zip(ps.keys, (v.type for v in ps.values), strict=True))
    assert types == {"engUnit": 12, "Quality": 3}


def test_narrow_signed_ints_accept_sign_extended_encoding() -> None:
    raw = pb.Payload()
    m = raw.metrics.add()
    m.name, m.datatype, m.int_value = "i8", 1, 2**32 - 1  # -1 sign-extended to 32 bits
    (out,) = decode_payload(raw.SerializeToString())["metrics"]
    assert out["value"] == -1


@pytest.mark.parametrize(
    ("datatype", "value"),
    [
        (DataType.INT32, 2**31),
        (DataType.UINT32, -1),
        (DataType.INT64, 1.5),
        (DataType.BOOLEAN, 1),
        (DataType.STRING, 3),
        (DataType.DOUBLE, "3"),
    ],
)
def test_invalid_values_rejected(datatype: DataType, value: object) -> None:
    with pytest.raises(ValueError):
        encode_payload([{"name": "x", "datatype": datatype, "value": value}])  # type: ignore[typeddict-item]


def test_seq_range_enforced() -> None:
    with pytest.raises(ValueError):
        ddata([], seq=256)


def test_nbirth_has_bdseq_and_rebirth_and_seq_zero() -> None:
    extra = MetricDict(name="Properties/Version", datatype=DataType.STRING, value="1.0")
    decoded = decode_payload(nbirth(3, [extra], timestamp=TS))
    assert decoded["seq"] == 0
    names = [m["name"] for m in decoded["metrics"]]
    assert names == [BDSEQ_METRIC, REBIRTH_METRIC, "Properties/Version"]
    assert decoded["metrics"][0]["datatype"] == DataType.INT64
    assert decoded["metrics"][0]["value"] == 3
    assert decoded["metrics"][1] | {"timestamp": None} == {
        "name": REBIRTH_METRIC,
        "datatype": DataType.BOOLEAN,
        "value": False,
        "timestamp": None,
        "is_null": False,
        "properties": {},
    }


def test_ndeath_has_only_bdseq_and_no_seq() -> None:
    decoded = decode_payload(ndeath(9, timestamp=TS))
    assert decoded["seq"] is None
    assert [(m["name"], m["value"]) for m in decoded["metrics"]] == [(BDSEQ_METRIC, 9)]


def test_device_messages() -> None:
    metrics = [MetricDict(name="power_kw", datatype=DataType.DOUBLE, value=7.5, timestamp=TS)]
    for builder in (dbirth, ddata):
        decoded = decode_payload(builder(metrics, 12, timestamp=TS))
        assert decoded["seq"] == 12
        assert decoded["metrics"][0]["value"] == 7.5
    death = decode_payload(ddeath(13, timestamp=TS))
    assert death == {"timestamp": TS, "seq": 13, "metrics": []}


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("plant-01", "NBIRTH", "line-01"), "spBv1.0/plant-01/NBIRTH/line-01"),
        (("plant-01", "NDEATH", "line-01"), "spBv1.0/plant-01/NDEATH/line-01"),
        (("plant-01", "NCMD", "line-01"), "spBv1.0/plant-01/NCMD/line-01"),
        (("plant-01", "DBIRTH", "line-01", "cnc-01"), "spBv1.0/plant-01/DBIRTH/line-01/cnc-01"),
        (("plant-01", "DDATA", "line-02", "press-01"), "spBv1.0/plant-01/DDATA/line-02/press-01"),
        (("plant-01", "DDEATH", "line-01", "cnc-01"), "spBv1.0/plant-01/DDEATH/line-01/cnc-01"),
    ],
)
def test_topic_round_trip(args: tuple[str, ...], expected: str) -> None:
    topic = build_topic(*args)
    assert topic == expected
    parsed = parse_topic(topic)
    assert parsed == Topic(
        args[0], MessageType(args[1]), args[2], args[3] if len(args) == 4 else None
    )
    assert str(parsed) == expected


@pytest.mark.parametrize(
    "args",
    [
        ("plant-01", "DDATA", "line-01"),
        ("plant-01", "NBIRTH", "line-01", "cnc-01"),
        ("plant/01", "NBIRTH", "line-01"),
        ("plant-01", "NBIRTH", "+"),
        ("plant-01", "BOGUS", "line-01"),
    ],
)
def test_build_topic_rejects_invalid(args: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        build_topic(*args)


@pytest.mark.parametrize(
    "topic",
    [
        "spBv1.0/plant-01/DDATA/line-01",
        "spBv1.0/plant-01/NDATA/line-01/cnc-01",
        "spBv1.0/plant-01/XDATA/line-01",
        "spBv2.0/plant-01/NBIRTH/line-01",
        "spBv1.0//NBIRTH/line-01",
        "twinvoice/cmd/cnc-01/set_load",
    ],
)
def test_parse_topic_rejects_invalid(topic: str) -> None:
    with pytest.raises(ValueError):
        parse_topic(topic)
