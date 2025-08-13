from __future__ import annotations

import argparse
import os
from .server import mcp
from .logging_setup import configure_logging


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run BibleFight MCP server")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--log-level", default=os.getenv("BIBLEFIGHT_LOG_LEVEL", "INFO"), help="Set log level (INFO, DEBUG, WARNING, ERROR)")
    args = parser.parse_args()

    level = "DEBUG" if args.debug else args.log_level
    configure_logging(level)
    mcp.run()
