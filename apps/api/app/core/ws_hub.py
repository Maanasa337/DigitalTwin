"""`/ws/live` fan-out: Valkey pub/sub channels → subscribed browser sockets, plus a 20 s heartbeat."""

import asyncio
import contextlib
import json
import logging
import re
from datetime import UTC, datetime

import valkey.asyncio as valkey
from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

HEARTBEAT_S = 20
TOPIC_RE = re.compile(r"^(asset:[a-z0-9][a-z0-9_-]*|alarms|voice:[A-Za-z0-9-]+)$")


def channel_to_topic(channel: str) -> str:
    if channel.startswith("live:"):
        return "asset:" + channel.removeprefix("live:")
    return channel


def to_client_message(topic: str, raw: str | bytes) -> dict:
    data = json.loads(raw)
    message = {"type": data["kind"], **data["payload"]}
    if topic.startswith("asset:"):
        message.setdefault("asset", topic.removeprefix("asset:"))
    return message


class WsHub:
    def __init__(self, valkey_url: str) -> None:
        self._valkey_url = valkey_url
        self._sockets: dict[WebSocket, set[str]] = {}
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self._listen()), asyncio.create_task(self._heartbeat())]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def handle(self, ws: WebSocket) -> None:
        self._sockets[ws] = set()
        try:
            while True:
                msg = await ws.receive_json()
                topics = {t for t in msg.get("topics", []) if isinstance(t, str) and TOPIC_RE.match(t)}
                if msg.get("type") == "subscribe":
                    self._sockets[ws] |= topics
                elif msg.get("type") == "unsubscribe":
                    self._sockets[ws] -= topics
                await ws.send_json({"type": "subscribed", "topics": sorted(self._sockets[ws])})
        except (WebSocketDisconnect, ValueError):
            pass
        finally:
            self._sockets.pop(ws, None)

    async def publish_local(self, topic: str, message: dict) -> None:
        targets = [ws for ws, topics in self._sockets.items() if topic in topics]
        await self._send_all(targets, message)

    async def _send_all(self, sockets: list[WebSocket], message: dict) -> None:
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                self._sockets.pop(ws, None)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            await self._send_all(list(self._sockets), {"type": "heartbeat", "t": datetime.now(UTC).isoformat()})

    async def _listen(self) -> None:
        backoff = 1
        while True:
            try:
                client = valkey.from_url(self._valkey_url)
                async with client.pubsub() as pubsub:
                    await pubsub.psubscribe("live:*", "voice:*")
                    await pubsub.subscribe("alarms")
                    backoff = 1
                    while True:
                        # listen() raises after a few idle seconds in valkey-py; polling with a timeout does not.
                        item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if item is None:
                            continue
                        channel = item["channel"].decode()
                        topic = channel_to_topic(channel)
                        try:
                            await self.publish_local(topic, to_client_message(topic, item["data"]))
                        except (ValueError, KeyError, TypeError):
                            log.warning("dropping malformed live message", extra={"channel": channel})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("valkey subscriber disconnected", extra={"error": str(exc), "retry_s": backoff})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
