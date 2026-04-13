from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.middlewares.auth import AuthMiddleware
from app.routes import sensing
from app.socket_handler import cancel_all_heartbeats, sio

fastapi_app = FastAPI(title="Tech Sensing Platform")


@fastapi_app.on_event("startup")
async def startup_event():
    from core.sensing.scheduler import start_scheduler
    await start_scheduler()


@fastapi_app.on_event("shutdown")
async def shutdown_event():
    await cancel_all_heartbeats()


excluded_routes = [("POST", "/user"), ("POST", "/user/login")]
fastapi_app.add_middleware(
    AuthMiddleware,
    included_paths=["/sensing", "/user"],
    excluded_routes=excluded_routes,
)

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
