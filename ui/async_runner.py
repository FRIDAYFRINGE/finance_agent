import asyncio
import atexit
import logging
import threading
from typing import Any, Coroutine, Optional

import streamlit as st

from agent.mcp_client import MCPClient

logger = logging.getLogger("ui.async_runner")

_WORKER_LOCK = threading.Lock()
_ACTIVE_WORKER: Optional["AsyncWorker"] = None


class AsyncWorker:
    """Persistent background event loop thread manager for Streamlit."""

    def __init__(self):
        self._lock = threading.Lock()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._start_loop,
            name="StreamlitAsyncWorkerThread",
            daemon=True,
        )
        self.thread.start()
        self.mcp_client: Optional[MCPClient] = None
        self._is_stopped = False

    def _start_loop(self) -> None:
        """Entry point for the background worker thread."""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def run(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Executes a coroutine inside the persistent event loop and blocks for result."""
        if self._is_stopped:
            raise RuntimeError("Cannot dispatch coroutine: AsyncWorker has been stopped.")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def get_mcp_client(self) -> MCPClient:
        """Returns or lazily initializes the process-wide MCPClient inside the worker loop."""
        with self._lock:
            if self.mcp_client is None:
                logger.info("Initializing MCPClient inside AsyncWorker background loop...")
                client = MCPClient()
                self.run(client.start())
                self.mcp_client = client
                logger.info("MCPClient initialized successfully inside AsyncWorker.")
            return self.mcp_client

    def stop(self) -> None:
        """Cleanly terminates the MCP subprocess and stops the background event loop."""
        with self._lock:
            if self._is_stopped:
                return
            self._is_stopped = True

            if self.mcp_client is not None:
                try:
                    logger.info("Stopping MCPClient from AsyncWorker...")
                    future = asyncio.run_coroutine_threadsafe(self.mcp_client.stop(), self.loop)
                    future.result(timeout=5.0)
                except Exception as e:
                    logger.warning("Error stopping MCPClient during AsyncWorker teardown: %s", e)
                finally:
                    self.mcp_client = None

            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)


@atexit.register
def _cleanup_active_worker():
    """Ensures subprocess cleanup on process termination."""
    global _ACTIVE_WORKER
    if _ACTIVE_WORKER is not None:
        try:
            _ACTIVE_WORKER.stop()
        except Exception:
            pass
        _ACTIVE_WORKER = None


@st.cache_resource
def get_async_worker() -> AsyncWorker:
    """Returns the process-wide singleton AsyncWorker instance.
    
    Decorated with @st.cache_resource to persist across Streamlit script reruns.
    """
    global _ACTIVE_WORKER
    with _WORKER_LOCK:
        if _ACTIVE_WORKER is None or _ACTIVE_WORKER._is_stopped:
            _ACTIVE_WORKER = AsyncWorker()
        return _ACTIVE_WORKER
