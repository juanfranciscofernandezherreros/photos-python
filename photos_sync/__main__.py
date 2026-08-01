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
