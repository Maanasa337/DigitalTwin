"""Store-and-forward (FR-EDGE-03): nothing is lost while the broker is away, and order is kept."""

from pathlib import Path

from edge.buffer import StoreAndForward


def test_messages_drain_oldest_first(tmp_path: Path) -> None:
    box = StoreAndForward(tmp_path / "q.sqlite")
    for i in range(5):
        box.enqueue("twinvoice/pred/cnc-01", f"m{i}".encode())
    sent: list[bytes] = []
    assert box.drain(lambda _t, payload, _q: sent.append(payload) or True) == 5
    assert sent == [b"m0", b"m1", b"m2", b"m3", b"m4"]
    assert box.pending() == 0


def test_a_failed_publish_stops_the_drain_and_keeps_the_rest(tmp_path: Path) -> None:
    box = StoreAndForward(tmp_path / "q.sqlite")
    for i in range(4):
        box.enqueue("t", f"m{i}".encode())
    attempts = iter([True, True, False])
    assert box.drain(lambda *_: next(attempts)) == 2
    assert box.pending() == 2
    # The message that failed is retried first next time.
    sent: list[bytes] = []
    box.drain(lambda _t, payload, _q: sent.append(payload) or True)
    assert sent == [b"m2", b"m3"]


def test_the_queue_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "q.sqlite"
    box = StoreAndForward(path)
    box.enqueue("t", b"kept")
    box.close()
    assert StoreAndForward(path).pending() == 1
