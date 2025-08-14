from __future__ import annotations

import logging
import asyncio
import argparse
import os
from .server import mcp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BIBLEFIGHT")


def main():
    parser = argparse.ArgumentParser(description="Run BibleFight MCP server")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    try:
        asyncio.run(mcp.run_async())
    except KeyboardInterrupt:
        logger.info("🛑 Keyboard interrupt received. Shutting down...")
        exit(0)

if __name__ == "__main__":
    main()