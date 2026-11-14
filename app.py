"""
Live AI News Platform - command-line entry point.

    python app.py                 # API + web UI on HOST:PORT
    python app.py --stream        # ... plus background Serper polling / indexing
    python app.py --demo          # ... pre-loaded with fictional sample articles (no keys needed)
"""

from __future__ import annotations

import argparse
import logging

import uvicorn

from config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Live AI News Platform")
    parser.add_argument("--host", default=Config.HOST, help=f"bind address (default: {Config.HOST})")
    parser.add_argument("--port", type=int, default=Config.PORT, help=f"port (default: {Config.PORT})")
    stream = parser.add_mutually_exclusive_group()
    stream.add_argument(
        "--stream",
        dest="stream",
        action="store_true",
        default=None,
        help="continuously fetch and index news in the background",
    )
    stream.add_argument("--no-stream", dest="stream", action="store_false", help="disable background news fetching")
    parser.add_argument(
        "--demo",
        action="store_true",
        default=None,
        help="pre-load fictional sample articles so the UI can be tried without API keys",
    )
    args = parser.parse_args()

    logging.basicConfig(level=Config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from api.main import create_app

    app = create_app(enable_streaming=args.stream, demo=args.demo)
    uvicorn.run(app, host=args.host, port=args.port, log_level=Config.LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
