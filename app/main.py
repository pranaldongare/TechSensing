from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import socketio

from app.middlewares.auth import UserJwtPayload
from app.routes import sensing
from app.socket_handler import cancel_all_heartbeats, sio

fastapi_app = FastAPI(title="Tech Sensing Platform")


# Default user middleware — no login required
class DefaultUserMiddleware(BaseHTTPMiddleware):
    """Injects a default user into every request so routes work without auth."""
    async def dispatch(self, request: Request, call_next):
        request.state.user = UserJwtPayload(
            userId="default_user",
            name="Default User",
            email="user@techsensing.com",
        )
        return await call_next(request)


@fastapi_app.on_event("startup")
async def startup_event():
    from core.sensing.scheduler import start_scheduler
    await start_scheduler()


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    await cancel_all_heartbeats()


fastapi_app.add_middleware(DefaultUserMiddleware)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(sensing.router)


@fastapi_app.get("/health")
async def health():
    return {"status": "ok"}


app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
