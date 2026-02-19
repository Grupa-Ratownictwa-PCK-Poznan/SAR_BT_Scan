#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supervisor code:
- starts and monitors the main process
- wipes the database file on every start (you will still have older versions on the USB memory, this is left intact)
- logs events and errors
- every 60s creates a dump of database to selected path
  with naming: YYYY-MM-DD-HH-MM-SS-BTlog.db

Requires: Python 3.9+, Raspberry Pi OS
"""

import os
import sys
import time
import signal
import shutil
import logging
import subprocess
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

# Import settings for configuration
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from settings import CLEAN_DB_ON_STARTUP, USB_BACKUP_ENABLED
except ImportError:
    CLEAN_DB_ON_STARTUP = False  # Default fallback
    USB_BACKUP_ENABLED = False  # Default fallback

# --- Config through environment variables (see /etc/default/btscanner-supervisor) ---
MAIN_CMD = os.getenv("BTS_MAIN_CMD", "/opt/btscanner/main_scanner.py")
DB_PATH = Path(os.getenv("BTS_DB_PATH", "/opt/btscanner/data/BTlog.db"))
DEST_DIR = Path(os.getenv("BTS_DEST_DIR", "/mnt/pendrive"))
LOG_DIR = Path(os.getenv("BTS_LOG_DIR", "/var/log/btscanner"))
RESTART_BACKOFF_MAX = int(os.getenv("BTS_RESTART_BACKOFF_MAX", "60"))  # seconds
BACKUP_INTERVAL = int(os.getenv("BTS_BACKUP_INTERVAL", "60"))  # seconds
TIMEZONE = os.getenv("BTS_TIMEZONE", "local")  # "local" or "utc"
STOP_FILE = Path(os.getenv("BTS_STOP_FILE", "/run/btscanner-supervisor.stop"))
# If you use venv, set up something like: BTS_MAIN_CMD="/opt/btscanner/venv/bin/python /opt/btscanner/main_scanner.py"

# --- Logging ---
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "supervisor.log"

logger = logging.getLogger("btsupervisor")
logger.setLevel(logging.INFO)
fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(sh)

# --- Stan globalny ---
stop_event = threading.Event()
child_proc = None
child_lock = threading.Lock()


def now_for_stamp():
    if TIMEZONE.lower() == "utc":
        return datetime.now(timezone.utc)
    # default system time
    return datetime.now()


def make_timestamp_name():
    ts = now_for_stamp().strftime("%Y-%m-%d-%H-%M-%S")
    return f"{ts}-BTlog.db"


def sqlite_consistent_backup(src: Path, dst: Path):
    """
    It makes a consistent backup of SQLite using the backup() API, even when the file is in use.
    If it's not SQLite, it falls back to a regular copy.
    """
    try:
        # attempt to open file as SQLite
        with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as src_conn:
            with sqlite3.connect(dst) as dst_conn:
                src_conn.backup(dst_conn, pages=0, progress=None)
                dst_conn.commit()
        # fsync to target
        with open(dst, "rb+") as f:
            os.fsync(f.fileno())
        return True
    except sqlite3.Error as e:
        logger.warning(f"SQLite backup failed ({e}); attempting a normal copy")
        # fallback to a normal copy
        shutil.copy2(src, dst)
        with open(dst, "rb+") as f:
            os.fsync(f.fileno())
        return True
    except Exception as e:
        logger.error(f"Backupu error: {e}")
        return False


def do_minute_backup():
    """
    Backup thread runs every BACKUP_INTERVAL seconds.
    It assumes that DEST_DIR is mounted on-demand and unmounts after ~30 seconds of inactivity.
    """
    while not stop_event.is_set():
        try:
            if not USB_BACKUP_ENABLED:
                logger.debug("USB_BACKUP_ENABLED is False, skipping backup")
            elif DB_PATH.exists():
                DEST_DIR.mkdir(parents=True, exist_ok=True)

                # temp name and then move
                final_name = make_timestamp_name()
                tmp_name = f".{final_name}.tmp"
                dst_tmp = DEST_DIR / tmp_name
                dst_final = DEST_DIR / final_name

                ok = sqlite_consistent_backup(DB_PATH, dst_tmp)
                if ok:
                    os.replace(dst_tmp, dst_final)
                    logger.info(f"Backup OK -> {dst_final}")
                else:
                    # clean up the temp file in case of an issue
                    try:
                        if dst_tmp.exists():
                            dst_tmp.unlink()
                    except Exception:
                        pass
            else:
                logger.warning(f"No DB file: {DB_PATH}")
        except Exception as e:
            logger.exception(f"Exception when making backup: {e}")

        # await interval
        for _ in range(BACKUP_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)


def start_child():
    global child_proc
    with child_lock:
        if CLEAN_DB_ON_STARTUP:
            logger.info(f"Removing DB file (CLEAN_DB_ON_STARTUP=True): {DB_PATH}")
            Path(DB_PATH).unlink(missing_ok=True)
        else:
            logger.info(f"Keeping DB file (CLEAN_DB_ON_STARTUP=False): {DB_PATH}")
        logger.info(f"Start of the main process: {MAIN_CMD}")
        # If a single string is provided, run it with shell=True; we maintain flexibility.
        child_proc = subprocess.Popen(
            MAIN_CMD,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=os.setsid,  # own process group
        )
        threading.Thread(target=pipe_logger, args=(child_proc.stdout,), daemon=True).start()


def pipe_logger(pipe):
    # redirect stdout/stderr of a child process to logfile
    for line in iter(pipe.readline, ""):
        logger.info(f"[main] {line.rstrip()}")
    pipe.close()


def stop_child():
    global child_proc
    with child_lock:
        if child_proc and child_proc.poll() is None:
            logger.info("Closing of the main process (SIGTERM)...")
            try:
                os.killpg(os.getpgid(child_proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            # 10s for a graceful closure
            for _ in range(10):
                if child_proc.poll() is not None:
                    break
                time.sleep(1)
            if child_proc.poll() is None:
                logger.warning("No reaction, SIGKILL...")
                try:
                    os.killpg(os.getpgid(child_proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        child_proc = None


def handle_signal(signum, frame):
    logger.info(f"Signal received {signum}, closing.")
    stop_event.set()
    stop_child()


def supervise_loop():
    backoff = 1
    while not stop_event.is_set():
        if STOP_FILE.exists():
            logger.warning(f"Detected STOP_FILE {STOP_FILE} â supervisor is pausing restart.")
            time.sleep(5)
            continue

        start_child()
        exit_code = None
        while exit_code is None and not stop_event.is_set():
            try:
                exit_code = child_proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass

        if stop_event.is_set():
            break

        logger.error(f"Main process closed on (code={exit_code}). Restart on {backoff}s.")
        time.sleep(backoff)
        backoff = min(RESTART_BACKOFF_MAX, backoff * 2 if backoff < 8 else backoff + 5)


def main():
    # signals
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # backupu thread
    t_bak = threading.Thread(target=do_minute_backup, daemon=True)
    t_bak.start()

    # supervisor loop
    try:
        supervise_loop()
    except Exception:
        logger.exception("Supervisor unexpected exception.")
    finally:
        stop_event.set()
        stop_child()
        logger.info("Supervisor finished.")


if __name__ == "__main__":
    main()
