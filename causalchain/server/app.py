"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from causalchain.server.routes import make_router


def create_app(db_path: str | None = None) -> FastAPI:
    """Create the CausalChain API application."""
    app = FastAPI(title="CausalChain", version="0.1.0")
    app.include_router(make_router(db_path))
    return app


app = create_app()

