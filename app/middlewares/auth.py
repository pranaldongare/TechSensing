from fastapi import HTTPException, Request
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, EmailStr
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.config import settings


class UserJwtPayload(BaseModel):
    userId: str
    name: str
    email: EmailStr
    is_active: bool = True


def normalize_path(path: str) -> str:
    if path != "/" and path.endswith("/"):
        return path.rstrip("/")
    return path


def get_current_user_email(request: Request) -> str:
    """Dependency to get the current user's email from request state."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return user.email


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        included_paths: list[str] = None,
        excluded_routes: list[tuple[str, str]] = None,
    ):
        super().__init__(app)
        self.included_paths = included_paths or []
        self.excluded_routes = excluded_routes or []

    async def dispatch(self, request: Request, call_next):
        path = normalize_path(request.url.path)
        method = request.method.upper()

        print(f"Request path: {path}, method: {method}")

        if (method, path) in self.excluded_routes:
            return await call_next(request)

        if not any(path == p or path.startswith(p + "/") for p in self.included_paths):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        jwt_token = (
            auth_header.split(" ")[-1] if auth_header.startswith("Bearer ") else None
        )

        if not jwt_token:
            jwt_token = request.query_params.get("token")

        if not jwt_token:
            return JSONResponse(
                {"error": "Authorization header, query param, or JWT token missing"},
                status_code=401,
            )

        if not settings.SECRET_KEY:
            return JSONResponse(
                {"error": "Secret key is not set in the environment"},
                status_code=500,
            )

        try:
            payload = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=["HS256"])
            request.state.user = UserJwtPayload(**payload)
        except ExpiredSignatureError:
            return JSONResponse({"error": "JWT token has expired"}, status_code=401)
        except InvalidTokenError as e:
            return JSONResponse(
                {"error": f"Invalid JWT token: {str(e)}"}, status_code=401
            )
        except Exception as e:
            return JSONResponse(
                {"error": f"Failed to decode JWT token: {str(e)}"}, status_code=400
            )

        return await call_next(request)
