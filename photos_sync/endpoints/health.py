"""Lightweight application health endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ..db import get_engine, t_captures

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Report readiness only when the database schema matches the code."""
    try:
        with get_engine().connect() as connection:
            connection.execute(select(t_captures.c.capture_day).limit(1))
    except Exception as exc:
        raise HTTPException(503, "Database unavailable or schema migration required") from exc
    return {"status": "ok"}
