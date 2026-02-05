from collections import deque
from pathlib import Path
import json
import logging
import os
import signal
import sys
import threading
import time

from sys_tools import get_snapshot

# Ring buffer to store recent snapshots
SNAPSHOT_STORE = deque(maxlen=100)  # Store last 100 snapshots

def get_data_dir():
    """Get or create the data directory for storing snapshots and logs."""
    data_dir = Path.home() / ".sysdoctor"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

# Set up logging for daemon operations
log_file = get_data_dir() / "daemon.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename=str(log_file),
    filemode='a'
)

def get_snapshots_file():
    """Return path to snapshots.json"""
    return Path.home() / ".sysdoctor" / "snapshots.json"

def save_snapshots(snapshots):
    """Save deque to JSON file"""
    with open(get_snapshots_file(), "w") as f:
        json.dump(list(snapshots), f)

def load_snapshots():
    """Load JSON file back to deque, handle missing file"""
    try:
        with open(get_snapshots_file(), "r") as f:
            snapshots = json.load(f)
            SNAPSHOT_STORE.clear()
            max_items = SNAPSHOT_STORE.maxlen or len(snapshots)
            SNAPSHOT_STORE.extend(snapshots[-max_items:])
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass

def snapshot_collector(sample_interval_s: int = 10):
    """Background thread to collect snapshots periodically"""
    snapshot_count = 0
    
    logging.info(f"Snapshot collector started with interval {sample_interval_s}s")
    
    while True:
        try:
            snapshot = get_snapshot()
            snapshot['timestamp'] = time.time()
            SNAPSHOT_STORE.append(snapshot)
            
            snapshot_count += 1
            if snapshot_count % 10 == 0:  # Save every 10 snapshots
                save_snapshots(SNAPSHOT_STORE)
                logging.debug(f"Saved snapshots to disk (total collected: {snapshot_count})")
        except Exception as e:
            logging.error(f"Error collecting snapshot: {e}", exc_info=True)
        
        time.sleep(sample_interval_s)

def start_collector_thread(sample_interval_s: int = 10) -> threading.Thread:
    """Start the snapshot collector thread and return it.
    
    This function is designed to be called by the MCP server to start
    collecting snapshots in a background thread.
    
    Args:
        sample_interval_s: Interval between snapshots in seconds
        
    Returns:
        The started Thread object
    """
    thread = threading.Thread(target=snapshot_collector, args=(sample_interval_s,), daemon=True)
    thread.start()
    return thread

def get_pid_file():
    return get_data_dir() / "daemon.pid"

def is_daemon_running():
    # Check if PID file exists and process is alive
    pid_file = get_pid_file()
    if not pid_file.exists():
        return False
    
    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, ProcessLookupError):
        # Process doesn't exist or PID file is corrupted
        pid_file.unlink(missing_ok=True)
        return False

def daemonize():
    """Fork the process to run in background"""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            sys.exit(0)
    except OSError as e:
        logging.error(f"First fork failed: {e}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Second parent exits
            sys.exit(0)
    except OSError as e:
        logging.error(f"Second fork failed: {e}")
        sys.exit(1)
    
    # Redirect standard file descriptors to /dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'w') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    get_pid_file().unlink(missing_ok=True)
    sys.exit(0)


def start_daemon(sample_interval_s: int = 10):
    """Start the daemon process (this function becomes the daemon)"""
    if is_daemon_running():
        return False
    
    # Fork to background
    daemonize()
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Write PID file (after fork, so we have the child PID)
    with open(get_pid_file(), "w") as f:
        f.write(str(os.getpid()))
    
    snapshot_thread = threading.Thread(target=snapshot_collector, args=(sample_interval_s,), daemon=True)
    snapshot_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        get_pid_file().unlink(missing_ok=True)
        return True


def launch_daemon(sample_interval_s: int = 10):
    """Launch daemon from CLI without the CLI becoming the daemon"""
    if is_daemon_running():
        return True
    
    # Fork a child process to become the daemon
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process: wait a moment and return
            time.sleep(1)
            return is_daemon_running()
    except OSError:
        return False
    
    # Child process: become the daemon
    start_daemon(sample_interval_s)


def stop_daemon():
    """Stop the daemon process"""
    pid_file = get_pid_file()
    if not pid_file.exists():
        return True
    
    try:
        with open(pid_file, "r") as f:
            pid = int(f.read().strip())
        
        # Send termination signal
        os.kill(pid, 15)  # SIGTERM
        pid_file.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, ProcessLookupError):
        pid_file.unlink(missing_ok=True)
        return True


def get_recent_snapshots(count: int = 10):
    """Get recent snapshots for the CLI to use"""
    snapshots_file = get_snapshots_file()
    if not snapshots_file.exists():
        return []
    
    try:
        with open(snapshots_file, 'r') as f:
            snapshots = json.load(f)
            return snapshots[-count:] if snapshots else []
    except (json.JSONDecodeError, IOError):
        return []
