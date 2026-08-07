#!/usr/bin/env python3
"""
Watches kb/past_brds/ (and the rest of kb/, since a KB edit changes retrieval
too) for file changes and re-runs scripts/run_all.py automatically whenever
one is detected.

No new dependency: this polls file mtimes on an interval rather than using a
filesystem-events library (watchdog etc.), since a capstone-scope demo watcher
doesn't need OS-level inotify/FSEvents -- a 2-second poll is imperceptible for
this use case and keeps requirements.txt unchanged.

Usage:
    python scripts/watch.py                 # poll every 2s, run on any kb/ change
    python scripts/watch.py --interval 5
    python scripts/watch.py --once          # do a single check-and-run, then exit (useful for cron/launchd)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = REPO_ROOT / "kb"
RUN_ALL = REPO_ROOT / "scripts" / "run_all.py"


def snapshot():
    return {
        str(p): p.stat().st_mtime
        for p in KB_ROOT.rglob("*")
        if p.is_file()
    }


def run_pipeline(extra_args):
    print(f"\n>>> change detected -- running scripts/run_all.py {' '.join(extra_args)}\n", flush=True)
    subprocess.run([sys.executable, str(RUN_ALL), *extra_args], cwd=REPO_ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="check once and exit instead of looping (for cron/launchd)")
    parser.add_argument("run_all_args", nargs=argparse.REMAINDER, help="passed through to run_all.py, e.g. -- --no-smoke-test")
    args = parser.parse_args()

    extra_args = [a for a in args.run_all_args if a != "--"]

    last = snapshot()
    print(f"Watching {KB_ROOT} for changes (poll every {args.interval}s). Ctrl+C to stop.")

    if args.once:
        return

    try:
        while True:
            time.sleep(args.interval)
            current = snapshot()
            if current != last:
                changed = sorted(set(current) ^ set(last)) or [
                    p for p in current if current[p] != last.get(p)
                ]
                for p in changed[:10]:
                    print(f"  changed: {Path(p).relative_to(REPO_ROOT)}")
                last = current
                run_pipeline(extra_args)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
