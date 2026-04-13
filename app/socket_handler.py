import asyncio

import jwt
import socketio
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from core.config import settings

active_connections = set()
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    ping_timeout=400,
    ping_interval=20,
)

heartbeat_tasks = {}


@sio.event
async def connect(sid, environ, auth=None):
    print(f"[WebSocket] Client connecting: {sid}")

    token = (auth or {}).get("token") if isinstance(auth, dict) else None
    if not token:
        print(f"[WebSocket] Rejected {sid}: no auth token provided")
        raise ConnectionRefusedError("Authentication required")

    try:
        jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except (ExpiredSignatureError, InvalidTokenError, Exception) as e:
        print(f"[WebSocket] Rejected {sid}: invalid token — {e}")
        raise ConnectionRefusedError("Invalid or expired token")

    active_connections.add(sid)

    async def send_heartbeat():
        try:
            while True:
                await sio.emit("heartbeat", {"status": "processing..."}, to=sid)
                await asyncio.sleep(20)
        except asyncio.CancelledError:
            pass

    heartbeat_tasks[sid] = asyncio.create_task(send_heartbeat())
    print(f"[WebSocket] Client {sid} connected successfully")


@sio.event
async def disconnect(sid):
    print(f"[WebSocket] Client disconnecting: {sid}")
    active_connections.discard(sid)
    task = heartbeat_tasks.pop(sid, None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    print(f"[WebSocket] Client {sid} disconnected successfully")


def is_client_connected(sid):
    """Check if a client is connected."""
    return sid in active_connections


async def cancel_all_heartbeats():
    """Cancel all heartbeat tasks on server shutdown."""
    for sid, task in heartbeat_tasks.items():
        task.cancel()
    for sid, task in list(heartbeat_tasks.items()):
        try:
            await task
        except asyncio.CancelledError:
            pass
    heartbeat_tasks.clear()
    active_connections.clear()
