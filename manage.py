#!/usr/bin/env python3
"""Manage inventory-manager: start/stop/restart."""
import os
import signal
import sys
import time

PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.pid")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")


def get_pid():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            return int(f.read().strip())
    return None


def is_running(pid=None):
    pid = pid or get_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start():
    if is_running():
        pid = get_pid()
        print(f"Already running (PID {pid})")
        sys.exit(0)

    base = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(base, "venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = "python3"

    import subprocess
    log = open(LOG_FILE, "a")
    p = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=log, stderr=log, cwd=base, start_new_session=True,
    )
    with open(PID_FILE, "w") as f:
        f.write(str(p.pid))
    time.sleep(1)
    print(f"Started (PID {p.pid})")


def stop():
    pid = get_pid()
    if not pid or not is_running(pid):
        print("Not running")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return
    os.kill(pid, signal.SIGTERM)
    time.sleep(1)
    if is_running(pid):
        os.kill(pid, signal.SIGKILL)
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    print("Stopped")


def restart():
    stop()
    time.sleep(1)
    start()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    else:
        print("Usage: python manage.py [start|stop|restart]")
