"""
Read-only psutil/OS command stubs for an advisor-only CLI.
Each returns a result dict.
"""

import logging
import psutil
import socket
import time
from typing import Any, Dict, List, Optional

# Memory conversion constants
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

def get_snapshot() -> Dict[str, Any]:
    """Point-in-time host state (load, cpu, mem, disks, top procs)."""
    logging.debug("get_snapshot: capturing system state")
    snapshot_time = time.time()
    
    try:
        snapshot = {
            "timestamp": snapshot_time,
            "hostname": socket.gethostname(),
            
            # System-wide metrics
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total_gb": psutil.virtual_memory().total / BYTES_PER_GB,
                "available_gb": psutil.virtual_memory().available / BYTES_PER_GB,
                "percent_used": psutil.virtual_memory().percent
            },
            "load_avg": psutil.getloadavg(),  # 1min, 5min, 15min averages
            
            # Top processes (implemented)
            "top_cpu_processes": top_cpu(n=10)["top_cpu_processes"],
            "top_mem_processes": top_mem(n=10)["top_mem_processes"],
            
            # Disk info
            "disk_usage": disk_usage(top_n=5),
            
            # Network connections (TODO: implement connections_summary)
            # "network_connections": connections_summary(limit=50),
            
            # Disk I/O (TODO: implement disk_io_brief) 
            # "disk_io": disk_io_brief(sample_interval_s=1),
            
            # Network I/O (TODO: implement net_io_brief)
            # "network_io": net_io_brief(sample_interval_s=1),
        }
        
        logging.debug(f"get_snapshot: captured snapshot with {len(snapshot['top_cpu_processes'])} CPU processes, {len(snapshot['top_mem_processes'])} memory processes")
        return snapshot
        
    except Exception as e:
        logging.error(f"get_snapshot: failed to capture snapshot: {e}")
        return {
            "timestamp": snapshot_time,
            "hostname": socket.gethostname(),
            "error": str(e)
        }

def get_recent_metrics(window: str = "5m", interval_s: int = 3) -> Dict[str, Any]:
    """Aggregates over a short window (cpu/load/mem/disk/net, top pids)."""
    raise NotImplementedError

def top_cpu(n: int = 10) -> Dict[str, Any]:
    """Top-N processes by CPU%."""
    logging.debug(f"top_cpu: collecting processes for top {n}")
    processes = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    psutil.cpu_percent(interval=None)  # Start measurement (non-blocking)
    
    results = []
    access_denied_count = 0
    for proc in processes:
        try:
            cpu = proc.cpu_percent(interval=None)  # Non-blocking
            results.append({
                'pid': proc.pid,
                'name': proc.name(),
                'cpu_percent': cpu
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            access_denied_count += 1
            continue
    
    if access_denied_count > 0:
        logging.debug(f"top_cpu: {access_denied_count} processes inaccessible")
    
    top_procs = sorted(results, key=lambda x: x['cpu_percent'], reverse=True)[:n]
    logging.debug(f"top_cpu: found {len(results)} processes, returning top {len(top_procs)}")
    return {
        'top_cpu_processes': top_procs,
        'num_processes': len(results)
    }

def top_mem(n: int = 10) -> Dict[str, Any]:
    """Top-N processes by RSS/VMS."""
    logging.debug(f"top_mem: collecting memory info for top {n}")
    processes = []
    access_denied_count = 0
    
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            info = proc.info
            mem_info = info['memory_info']
            if mem_info:
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'],
                    'rss_mb': mem_info.rss / BYTES_PER_MB,
                    'vms_mb': mem_info.vms / BYTES_PER_MB
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            access_denied_count += 1
            continue
    
    if access_denied_count > 0:
        logging.debug(f"top_mem: {access_denied_count} processes inaccessible")
    
    # Sort by RSS (resident set size)
    top_procs = sorted(processes, key=lambda x: x['rss_mb'], reverse=True)[:n]
    logging.debug(f"top_mem: found {len(processes)} processes, returning top {len(top_procs)}")
    
    return {
        'top_mem_processes': top_procs,
        'total_processes': len(processes)
    }

def process_info(pid: int) -> Dict[str, Any]:
    """Details for one PID (cpu/mem/threads/fds/cmdline)."""
    raise NotImplementedError

def proc_tree(pid: int, depth: int = 2) -> Dict[str, Any]:
    """Parent/child view around PID up to depth."""
    raise NotImplementedError

def connections_summary(
    limit: int = 200, states: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Network conn counts + small samples; cap by limit/states."""
    raise NotImplementedError

def disk_usage(paths: Optional[List[str]] = None, top_n: int = 5) -> Dict[str, Any]:
    """Disk headroom per mount; optional focus on paths."""
    usage_info = []
    
    if paths:
        # Check specific paths
        for path in paths:
            try:
                usage = psutil.disk_usage(path)
                usage_info.append({
                    'location': path,
                    'type': 'path',
                    'total_gb': usage.total / BYTES_PER_GB,
                    'free_gb': usage.free / BYTES_PER_GB,
                    'percent_used': (usage.used / usage.total) * 100 if usage.total > 0 else 0
                })
            except (PermissionError, OSError, FileNotFoundError):
                usage_info.append({
                    'location': path,
                    'type': 'path',
                    'error': 'inaccessible'
                })
    else:
        # Get all mount points
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                usage_info.append({
                    'location': partition.mountpoint,
                    'type': 'mount',
                    'device': partition.device,
                    'fstype': partition.fstype,
                    'total_gb': usage.total / BYTES_PER_GB,
                    'free_gb': usage.free / BYTES_PER_GB,
                    'percent_used': (usage.used / usage.total) * 100 if usage.total > 0 else 0
                })
            except (PermissionError, OSError):
                continue
    
    # Sort by percent used and limit
    if not paths:
        usage_info = sorted(usage_info, key=lambda x: x.get('percent_used', 0), reverse=True)[:top_n]
    
    return {'usage': usage_info}
