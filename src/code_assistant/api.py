import hmac
import threading
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException

from code_assistant.config import Settings
from code_assistant.models import DebugRequest, DebugResponse
from code_assistant.workflow import debug_repository


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Agentic Code-Search & Debugging Assistant", version="0.1.0")
    capacity = threading.BoundedSemaphore(2)

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token:
            expected = "Bearer " + settings.api_token.get_secret_value()
            if not authorization or not hmac.compare_digest(authorization, expected):
                raise HTTPException(status_code=401, detail="invalid bearer token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.mode}

    @app.post("/v1/debug", response_model=DebugResponse, dependencies=[Depends(authorize)])
    def debug(request: DebugRequest) -> DebugResponse:
        try:
            root = settings.repository(request.repository)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not capacity.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="two runs are already active")
        try:
            return debug_repository(root, request.issue, settings)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        finally:
            capacity.release()

    return app


app = create_app()
