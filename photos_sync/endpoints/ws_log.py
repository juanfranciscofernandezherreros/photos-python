"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from ..observability import (
    WEBSOCKET_CONNECTIONS,
    WEBSOCKET_CONNECTIONS_TOTAL,
    log_event,
)
from ..web_server import (
    WebSocket,
    WebSocketDisconnect,
    asyncio,
    broadcaster,
)

router = APIRouter()

@router.websocket("/ws/log")
async def ws_log(ws: WebSocket):
    await ws.accept()
    WEBSOCKET_CONNECTIONS.labels(route="/ws/log").inc()
    WEBSOCKET_CONNECTIONS_TOTAL.labels(route="/ws/log").inc()
    log_event("websocket_connected", route="/ws/log")
    q: asyncio.Queue = asyncio.Queue()
    broadcaster.subscribe(q)
    try:
        for line in broadcaster.replay(q):
            await ws.send_text(line)
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30)
                await ws.send_text(msg)
            except asyncio.TimeoutError:
                await ws.send_text("")   # keepalive ping
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        broadcaster.unsubscribe(q)
        WEBSOCKET_CONNECTIONS.labels(route="/ws/log").dec()
        log_event("websocket_disconnected", route="/ws/log")
