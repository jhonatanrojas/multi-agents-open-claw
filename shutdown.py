#!/usr/bin/env python3
"""
shutdown.py - Graceful shutdown (F4.1)

Handle graceful shutdown on SIGTERM/SIGINT.
"""

import signal
import sys
from typing import List, Callable

_shutdown_handlers: List[Callable] = []


def register_shutdown_handler(handler: Callable) -> None:
    """Register a function to call on shutdown."""
    _shutdown_handlers.append(handler)


def _shutdown(signum, frame):
    """Handle shutdown signal."""
    print(f"\nReceived signal {signum}, shutting down gracefully...")
    
    for handler in _shutdown_handlers:
        try:
            handler()
        except Exception as e:
            print(f"Error in shutdown handler: {e}")
    
    sys.exit(0)


def setup_graceful_shutdown() -> None:
    """Setup graceful shutdown handlers."""
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)


__all__ = ["register_shutdown_handler", "setup_graceful_shutdown"]
