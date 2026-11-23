import os
import sys
import time
import subprocess

USERNAME = os.getenv("AUTOROX_USERNAME", "whatomate")
PASSWORD = os.getenv("AUTOROX_PASSWORD", "")
INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/live")

def run_sync():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting AutoRox live inventory sync...")
    cmd = [
        sys.executable,
        "sync_inventory.py",
        "-u", USERNAME,
        "-o", OUTPUT_DIR,
        "--update-db"
    ]
    if PASSWORD:
        cmd.extend(["-p", PASSWORD])

    try:
        res = subprocess.run(cmd, check=True)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sync finished with exit code {res.returncode}")
    except subprocess.CalledProcessError as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Sync failed: {e}")

if __name__ == "__main__":
    print(f"AutoRox Sync Worker initialized (User: {USERNAME}, Interval: {INTERVAL_MINUTES} mins)")
    # Run initial sync immediately on startup
    run_sync()

    # Loop sleep
    while True:
        time.sleep(INTERVAL_MINUTES * 60)
        run_sync()
