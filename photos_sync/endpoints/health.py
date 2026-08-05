"""Lightweight application health endpoint."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the HTTP application is ready to serve requests."""
    return {"status": "ok"}
