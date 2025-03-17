#!/usr/bin/env python

from common.md_to_yml import conversion_task
from common.yaml_docx_filler import docx_fill_task
from common.endpoint import app
import uvicorn
import subprocess
import threading
import signal
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def handle_shutdown(signum, frame) -> None:
    """Handle graceful shutdown of servers on SIGINT or SIGTERM signals."""
    print("\nShutting down servers gracefully...")
    sys.exit(0)


def run_mkdocs(host: str = "127.0.0.1") -> None:
    """Run MkDocs server using subprocess.

    Args:
        host: Host address to bind to
    """
    try:
        subprocess.run(["mkdocs", "serve", "-a", f"{host}:8000"], check=True)
    except KeyboardInterrupt:
        pass


def main():
    # Get environment, running development by default
    ENV = os.getenv("ENVIRONMENT", "development")
    host = "0.0.0.0" if ENV == "production" else "127.0.0.1"

    print(f"Starting in {ENV} mode")

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Run conversion tasks
    conversion_task()
    docx_fill_task()

    # Start MkDocs in a daemon thread
    mkdocs_thread = threading.Thread(target=run_mkdocs, args=(host,), daemon=True)
    mkdocs_thread.start()

    try:
        # Run FastAPI in main thread
        uvicorn.run(app, host=host, port=8080)
    except KeyboardInterrupt:
        print("\nShutting down servers...")


if __name__ == "__main__":
    main()
