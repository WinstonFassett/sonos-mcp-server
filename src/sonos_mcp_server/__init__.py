"""Sonos MCP Server - Control Sonos speakers via Model Context Protocol."""

__version__ = "0.1.0"
__author__ = "Winston Fassett"
__license__ = "MIT"

from .server import mcp

__all__ = ["mcp"]