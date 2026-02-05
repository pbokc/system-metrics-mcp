#!/usr/bin/env python3
"""
MCP Server for System Metrics

This server exposes system metrics tools via the Model Context Protocol.
It runs a background thread to collect system snapshots periodically.
"""

import sys
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Import our modules
from daemon import SNAPSHOT_STORE, start_collector_thread, load_snapshots, save_snapshots
from mcp_tools import (
    set_snapshot_buffer,
    get_snapshot_history,
    analyze_trends,
    find_process_history,
)
from sys_tools import get_snapshot, top_cpu, top_mem, disk_usage

# Create the MCP server instance
mcp = FastMCP("System Metrics MCP", json_response=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@mcp.tool()
def get_current_snapshot() -> dict:
    """Get current system state (CPU, memory, disk, top processes)"""
    return get_snapshot()


@mcp.tool()
def get_top_cpu_processes(n: int = 10) -> dict:
    """Get top N processes by CPU usage
    
    Args:
        n: Number of processes to return (default: 10)
    """
    return top_cpu(n=n)


@mcp.tool()
def get_top_memory_processes(n: int = 10) -> dict:
    """Get top N processes by memory usage
    
    Args:
        n: Number of processes to return (default: 10)
    """
    return top_mem(n=n)


@mcp.tool()
def check_disk_usage(paths: Optional[list[str]] = None, top_n: int = 5) -> dict:
    """Check disk usage for all mounts or specific paths
    
    Args:
        paths: Optional list of specific paths to check
        top_n: Number of mounts to return when checking all (default: 5)
    """
    return disk_usage(paths=paths, top_n=top_n)


@mcp.tool()
def get_snapshot_history(last_n: int = 10, minutes_ago: Optional[int] = None) -> dict:
    """Get historical snapshots from the ring buffer
    
    Args:
        last_n: Number of recent snapshots to return (default: 10)
        minutes_ago: Optional - get snapshots from approximately N minutes ago
    """
    args = {"last_n": last_n}
    if minutes_ago is not None:
        args["minutes_ago"] = minutes_ago
    return get_snapshot_history(args)


@mcp.tool()
def analyze_trends(metric: str = "both", window_minutes: int = 10) -> dict:
    """Analyze CPU/memory trends over time from snapshot history
    
    Args:
        metric: Which metric to analyze - "cpu", "memory", or "both" (default: "both")
        window_minutes: Time window to analyze in minutes (default: 10)
    """
    return analyze_trends({"metric": metric, "window_minutes": window_minutes})


@mcp.tool()
def find_process_history(process_name: str, pid: Optional[int] = None) -> dict:
    """Track a specific process across snapshots
    
    Args:
        process_name: Name of process to track (required)
        pid: Optional PID of process to track
    """
    args = {"process_name": process_name}
    if pid is not None:
        args["pid"] = pid
    return find_process_history(args)


def main():
    """Initialize and run the MCP server"""
    logger.info("Starting System Metrics MCP Server")
    
    # Load existing snapshots from disk
    try:
        load_snapshots()
        logger.info(f"Loaded {len(SNAPSHOT_STORE)} existing snapshots from disk")
    except Exception as e:
        logger.warning(f"Could not load existing snapshots: {e}")
    
    # Wire up the snapshot buffer for tool functions
    set_snapshot_buffer(SNAPSHOT_STORE)
    logger.info("Snapshot buffer wired up")
    
    # Start the collector thread (runs in background)
    collector_thread = start_collector_thread(sample_interval_s=10)
    logger.info("Snapshot collector thread started")
    
    # Register signal handlers for graceful shutdown
    import signal
    import atexit
    
    def shutdown_handler():
        """Save snapshots before shutdown"""
        logger.info("Shutting down, saving snapshots...")
        try:
            save_snapshots(SNAPSHOT_STORE)
            logger.info(f"Saved {len(SNAPSHOT_STORE)} snapshots to disk")
        except Exception as e:
            logger.error(f"Error saving snapshots on shutdown: {e}")
    
    def signal_handler(signum, frame):
        """Handle shutdown signals"""
        shutdown_handler()
        sys.exit(0)
    
    atexit.register(shutdown_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the MCP server with stdio transport
    logger.info("MCP server ready, using stdio transport")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
