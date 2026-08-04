"""Entry point for ``python -m photos_sync`` and the ``photos-sync-web`` CLI command."""
from __future__ import annotations

import argparse


def main() -> None:
    """Start the Photos Sync web server."""
    parser = argparse.ArgumentParser(
        prog="photos-sync-web",
        description="Start the Photos Sync web dashboard",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    # Initialise the database engine and create tables if they don't exist yet.
    # This runs before uvicorn so it works even when lifespan hooks aren't fired
    # (e.g. during smoke-tests with --help or first boot on a fresh DB).
    try:

        from .db import get_engine, init_db
        # Honour DATABASE_URL env var — the engine singleton reads it on first use
        engine = get_engine()
        init_db(engine)
    except Exception as e:
        print(f"⚠️  Database init warning: {e}")

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn[standard]")
        raise SystemExit(1)

    uvicorn.run(
        "photos_sync.web_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
