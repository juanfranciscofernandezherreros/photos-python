"""Endpoint implemented in its own router module."""
from __future__ import annotations

from fastapi import APIRouter

from .. import web_server as _shared

# Endpoint implementations retain access to the application's shared services,
# models and state without duplicating business infrastructure.
globals().update({
    name: value
    for name, value in vars(_shared).items()
    if not name.startswith("__")
})

router = APIRouter()

@router.websocket("/ws/log")
async def ws_log(ws: WebSocket):
    await ws.accept()
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
