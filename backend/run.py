"""
Backend entry point.
Sets WindowsProactorEventLoopPolicy BEFORE uvicorn creates the event loop,
which is required for Playwright to spawn the Chromium subprocess on Windows.
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
