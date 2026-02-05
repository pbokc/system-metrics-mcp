import logging
import time
from typing import Any, Dict
from collections import deque

# Import available sys_tools functions
from sys_tools import get_snapshot, top_cpu, top_mem, disk_usage

# Global reference to snapshot buffer (will be set by main application)
_snapshot_buffer = None

# Define available tools for the LLM
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_snapshot",
            "description": "Get current system state (CPU, memory, disk, top processes)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "get_top_cpu_processes",
            "description": "Get top N processes by CPU usage",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of processes to return", "default": 10}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_memory_processes", 
            "description": "Get top N processes by memory usage",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of processes to return", "default": 10}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_disk_usage",
            "description": "Check disk usage for all mounts or specific paths",
            "parameters": {
                "type": "object", 
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}, "description": "Specific paths to check"},
                    "top_n": {"type": "integer", "description": "Number of mounts to return", "default": 5}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_snapshot_history",
            "description": "Get historical snapshots from the ring buffer",
            "parameters": {
                "type": "object",
                "properties": {
                    "last_n": {"type": "integer", "description": "Number of recent snapshots to return", "default": 10},
                    "minutes_ago": {"type": "integer", "description": "Get snapshots from N minutes ago (approximate)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "analyze_trends",
            "description": "Analyze CPU/memory trends over time from snapshot history",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["cpu", "memory", "both"], "description": "Which metric to analyze", "default": "both"},
                    "window_minutes": {"type": "integer", "description": "Time window to analyze in minutes", "default": 10}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_process_history",
            "description": "Track a specific process across snapshots",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {"type": "string", "description": "Name of process to track"},
                    "pid": {"type": "integer", "description": "PID of process to track (optional)"}
                },
                "required": ["process_name"]
            }
        }
    }
]

def set_snapshot_buffer(buffer: deque):
    """Set the global snapshot buffer reference."""
    global _snapshot_buffer
    _snapshot_buffer = buffer

def execute_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool call and return the result."""
    try:
        if tool_name == "get_current_snapshot":
            return get_snapshot()
        elif tool_name == "get_top_cpu_processes":
            n = arguments.get("n", 10)
            return top_cpu(n=n)
        elif tool_name == "get_top_memory_processes":
            n = arguments.get("n", 10) 
            return top_mem(n=n)
        elif tool_name == "check_disk_usage":
            paths = arguments.get("paths")
            top_n = arguments.get("top_n", 5)
            return disk_usage(paths=paths, top_n=top_n)
        elif tool_name == "get_snapshot_history":
            return get_snapshot_history(arguments)
        elif tool_name == "analyze_trends":
            return analyze_trends(arguments)
        elif tool_name == "find_process_history":
            return find_process_history(arguments)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logging.error(f"Tool execution error for {tool_name}: {e}")
        return {"error": str(e)}

def get_snapshot_history(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get historical snapshots from the ring buffer."""
    if not _snapshot_buffer:
        return {"error": "No snapshot buffer available"}
    
    last_n = args.get("last_n", 10)
    minutes_ago = args.get("minutes_ago")
    
    if minutes_ago:
        # Find snapshots from approximately N minutes ago
        target_time = time.time() - (minutes_ago * 60)
        relevant_snapshots = []
        for snapshot in _snapshot_buffer:
            if abs(snapshot["timestamp"] - target_time) < 300:  # Within 5 minutes
                relevant_snapshots.append({
                    "timestamp": snapshot["timestamp"],
                    "cpu_percent": snapshot["cpu_percent"],
                    "memory_percent": snapshot["memory"]["percent_used"],
                    "load_avg": snapshot["load_avg"]
                })
        return {"snapshots": relevant_snapshots[:last_n]}
    else:
        # Get the last N snapshots
        recent_snapshots = list(_snapshot_buffer)[-last_n:]
        simplified = []
        for snapshot in recent_snapshots:
            simplified.append({
                "timestamp": snapshot["timestamp"],
                "cpu_percent": snapshot["cpu_percent"], 
                "memory_percent": snapshot["memory"]["percent_used"],
                "load_avg": snapshot["load_avg"],
                "top_cpu_process": snapshot["top_cpu_processes"][0]["name"] if snapshot["top_cpu_processes"] else "unknown",
                "top_memory_process": snapshot["top_mem_processes"][0]["name"] if snapshot["top_mem_processes"] else "unknown"
            })
        return {"snapshots": simplified}

def analyze_trends(args: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze CPU/memory trends over time."""
    if not _snapshot_buffer or len(_snapshot_buffer) < 2:
        return {"error": "Insufficient snapshot history for trend analysis"}
    
    metric = args.get("metric", "both")
    window_minutes = args.get("window_minutes", 10)
    
    # Get snapshots within the time window
    cutoff_time = time.time() - (window_minutes * 60)
    relevant_snapshots = [s for s in _snapshot_buffer if s["timestamp"] >= cutoff_time]
    
    if len(relevant_snapshots) < 2:
        return {"error": f"Not enough snapshots in the last {window_minutes} minutes"}
    
    trends = {}
    
    if metric in ["cpu", "both"]:
        cpu_values = [s["cpu_percent"] for s in relevant_snapshots]
        trends["cpu"] = {
            "min": min(cpu_values),
            "max": max(cpu_values),
            "avg": sum(cpu_values) / len(cpu_values),
            "current": cpu_values[-1],
            "change": cpu_values[-1] - cpu_values[0],
            "trend": "increasing" if cpu_values[-1] > cpu_values[0] else "decreasing"
        }
    
    if metric in ["memory", "both"]:
        mem_values = [s["memory"]["percent_used"] for s in relevant_snapshots]
        trends["memory"] = {
            "min": min(mem_values),
            "max": max(mem_values), 
            "avg": sum(mem_values) / len(mem_values),
            "current": mem_values[-1],
            "change": mem_values[-1] - mem_values[0],
            "trend": "increasing" if mem_values[-1] > mem_values[0] else "decreasing"
        }
    
    return {
        "time_window_minutes": window_minutes,
        "snapshots_analyzed": len(relevant_snapshots),
        "trends": trends
    }

def find_process_history(args: Dict[str, Any]) -> Dict[str, Any]:
    """Track a specific process across snapshots."""
    if not _snapshot_buffer:
        return {"error": "No snapshot buffer available"}
    
    process_name = args.get("process_name")
    target_pid = args.get("pid")
    
    process_history = []
    
    for snapshot in _snapshot_buffer:
        # Check both CPU and memory process lists
        found_processes = []
        
        for proc in snapshot.get("top_cpu_processes", []):
            if (proc["name"] == process_name and 
                (not target_pid or proc["pid"] == target_pid)):
                found_processes.append({
                    "timestamp": snapshot["timestamp"],
                    "pid": proc["pid"],
                    "cpu_percent": proc["cpu_percent"],
                    "type": "cpu_list"
                })
        
        for proc in snapshot.get("top_mem_processes", []):
            if (proc["name"] == process_name and 
                (not target_pid or proc["pid"] == target_pid)):
                # Avoid duplicates if process is in both lists
                existing = next((p for p in found_processes 
                               if p["timestamp"] == snapshot["timestamp"] and p["pid"] == proc["pid"]), None)
                if existing:
                    existing["rss_mb"] = proc["rss_mb"]
                    existing["type"] = "both_lists"
                else:
                    found_processes.append({
                        "timestamp": snapshot["timestamp"],
                        "pid": proc["pid"],
                        "rss_mb": proc["rss_mb"],
                        "type": "memory_list"
                    })
        
        process_history.extend(found_processes)
    
    return {
        "process_name": process_name,
        "target_pid": target_pid,
        "history": process_history[-20:]  # Last 20 occurrences
    }

def format_snapshot_context(snapshot_buffer: deque) -> str:
    """Format recent snapshots for context."""
    if not snapshot_buffer:
        return "No recent snapshots available."
    
    # Get the most recent snapshot
    latest = snapshot_buffer[-1]
    
    context = f"""Recent System State:
- Timestamp: {latest['timestamp']}
- CPU Usage: {latest['cpu_percent']}%
- Memory: {latest['memory']['percent_used']}% used ({latest['memory']['available_gb']:.1f}GB free)
- Load Average: {latest['load_avg']}
- Top CPU Process: {latest['top_cpu_processes'][0]['name']} ({latest['top_cpu_processes'][0]['cpu_percent']}%)
- Top Memory Process: {latest['top_mem_processes'][0]['name']} ({latest['top_mem_processes'][0]['rss_mb']:.1f}MB)
"""
    
    # If we have multiple snapshots, show trend
    if len(snapshot_buffer) > 1:
        older = snapshot_buffer[-5] if len(snapshot_buffer) >= 5 else snapshot_buffer[0]
        cpu_trend = latest['cpu_percent'] - older['cpu_percent']
        mem_trend = latest['memory']['percent_used'] - older['memory']['percent_used']
        
        context += f"""
Recent Trends:
- CPU: {"+" if cpu_trend > 0 else ""}{cpu_trend:.1f}% change
- Memory: {"+" if mem_trend > 0 else ""}{mem_trend:.1f}% change
"""
    
    return context
