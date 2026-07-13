import os

from fastapi import Request
from fastapi.responses import JSONResponse

_TOKEN = os.getenv("API_TOKEN", "pixfabrica-dev-token")


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Health check is public
    if path == "/health":
        return await call_next(request)
    # Font previews — loaded by @font-face; browsers cannot send Authorization
    if path.startswith("/fonts/files/"):
        return await call_next(request)
    # Gallery thumbnails — loaded by <img>; browsers cannot send Authorization
    if path.startswith("/gallery/thumbnails/"):
        return await call_next(request)
    # CORS preflight — let the CORS middleware handle it
    if request.method == "OPTIONS":
        return await call_next(request)
    # WebSocket upgrades — browser cannot send Authorization headers
    if request.headers.get("upgrade", "").lower() == "websocket":
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if token != _TOKEN:
        return JSONResponse({"detail": "Invalid or missing token"}, status_code=401)
    return await call_next(request)
