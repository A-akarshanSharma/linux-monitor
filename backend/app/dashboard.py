"""Serve a packaged dashboard without a second web server."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class DashboardFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        # API misses must keep their JSON 404, even if a file named api exists.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if path.startswith("assets/") and response.status_code == 200
            else "no-cache"
        )
        return response
