#!/usr/bin/env python3

import fcntl
import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SDIR = ROOT / "scheduler"
CONFIG = SDIR / "config.json"
STATE = SDIR / "today.json"
STATE_LOCK = SDIR / ".state.lock"
BEGIN = "# BEGIN NAUKRI GENERATED JOBS"
END = "# END NAUKRI GENERATED JOBS"


def notify(message):
    """Send a Discord notification without disrupting scheduler execution."""
    import urllib.error

    try:
        webhook = load_env().get("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook:
            print("Discord notification skipped: webhook is not configured.")
            return

        payload = json.dumps({"content": message[:1900]}).encode("utf-8")
        request = urllib.request.Request(
            webhook,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "NaukriScheduler/1.0",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"Discord notification sent (HTTP {response.status}).")

    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"Discord notification failed: HTTP {exc.code}: {detail}")
    except Exception as exc:
        print(f"Discord notification failed: {type(exc).__name__}: {exc}")


@contextmanager
def locked(path, blocking=True):
    with path.open("a+") as handle:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        fcntl.flock(handle, flags)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_config():
    cfg = json.loads(CONFIG.read_text())
    count = int(cfg["updates_per_day"])
    windows = cfg["windows"]

    if count < 2 or count > len(windows):
        raise ValueError("updates_per_day must be between 2 and the window count")
    if windows[0]["action"] != "headline":
        raise ValueError("Window 1 must guarantee a headline update")
    if windows[1]["action"] != "resume":
        raise ValueError("Window 2 must guarantee a resume upload")

    allowed = {"headline", "resume", "both", "random"}
    for window in windows[:count]:
        if window["action"] not in allowed:
            raise ValueError(f"Invalid action: {window['action']}")
        start = minutes(window["start"])
        end = minutes(window["end"])
        if start >= end:
            raise ValueError("Each window's start must be before its end")

    options = cfg["random_action_options"]
    if not options or any(x not in {"headline", "resume", "both"} for x in options):
        raise ValueError("Invalid random_action_options")
    return cfg


def minutes(value):
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time: {value}")
    h, m = map(int, parts)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"Invalid time: {value}")
    return h * 60 + m


def save_state(state):
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n")
    os.chmod(temp, 0o600)
    temp.replace(STATE)


def install_generated_jobs(runs):
    result = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr or "Unable to read crontab")

    lines = result.stdout.splitlines()
    kept = []
    inside = False

    for line in lines:
        if line.strip() == BEGIN:
            inside = True
            continue
        if line.strip() == END:
            inside = False
            continue
        if not inside:
            kept.append(line)

    jobs = [BEGIN]
    for run in sorted(runs, key=lambda item: item["time"]):
        hour, minute = map(int, run["time"].split(":"))
        command = (
            f"cd {ROOT} && /usr/bin/python3 "
            f"scheduler/scheduler.py run {run['id']} "
            f">> scheduler/cron.log 2>&1"
        )
        jobs.append(f"{minute} {hour} * * * {command}")
    jobs.append(END)

    output = "\n".join(kept).rstrip() + "\n\n"
    output += "\n".join(jobs) + "\n"

    subprocess.run(
        ["crontab", "-"], input=output, text=True, check=True
    )


def generate(force=False):
    cfg = read_config()
    now = datetime.now(ZoneInfo(cfg["timezone"]))
    today = now.date().isoformat()

    with locked(STATE_LOCK):
        if force:
            first_window_start = min(
                minutes(w["start"])
                for w in cfg["windows"][:cfg["updates_per_day"]]
            )
            current_minute = now.hour * 60 + now.minute
            if current_minute >= first_window_start:
                raise ValueError(
                    "Cannot regenerate after the first update window has begun. "
                    "The existing schedule has been preserved."
                )

        if STATE.exists():
            old = json.loads(STATE.read_text())
            if old.get("date") == today and not force:
                runs = old["runs"]
                print(f"Keeping the existing schedule for {today}.")
            else:
                runs = create_runs(cfg, today)
                save_state({
                    "date": today,
                    "timezone": cfg["timezone"],
                    "runs": runs
                })
        else:
            runs = create_runs(cfg, today)
            save_state({
                "date": today,
                "timezone": cfg["timezone"],
                "runs": runs
            })

    install_generated_jobs(runs)

    print(f"Schedule installed for {today} ({cfg['timezone']}):")
    for run in sorted(runs, key=lambda item: item["time"]):
        print(f"  {run['time']} — {run['action']}")

    details = "\n".join(
        f"• {run['time']} IST — {run['action']}"
        for run in sorted(runs, key=lambda item: item["time"])
    )
    notify(f"📅 **Naukri schedule ready — {today}**\n{details}")


def create_runs(cfg, today):
    used = set()
    runs = []

    for index, window in enumerate(cfg["windows"][:cfg["updates_per_day"]]):
        start, end = minutes(window["start"]), minutes(window["end"])
        available = [m for m in range(start, end) if m not in used]
        if not available:
            raise ValueError("No unique minute available in a configured window")

        selected = random.SystemRandom().choice(available)
        used.add(selected)

        action = window["action"]
        if action == "random":
            action = random.SystemRandom().choice(cfg["random_action_options"])

        runs.append({
            "id": index + 1,
            "time": f"{selected // 60:02d}:{selected % 60:02d}",
            "action": action,
            "status": "pending",
            "attempts": 0
        })

    return runs


def load_env():
    env = {}
    for raw in (ROOT / ".env").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def _run_update(run_id):
    cfg = read_config()
    tz = ZoneInfo(cfg["timezone"])
    run_lock = SDIR / f".run-{run_id}.lock"

    with locked(run_lock, blocking=False):
        for attempt in range(1, 4):
            with locked(STATE_LOCK):
                if not STATE.exists():
                    print("No schedule exists.")
                    return

                state = json.loads(STATE.read_text())
                if state.get("date") != datetime.now(tz).date().isoformat():
                    print("Refusing to execute a stale schedule.")
                    return

                run = next(
                    (item for item in state["runs"] if item["id"] == run_id),
                    None
                )
                if run is None or run["status"] != "pending":
                    print(f"Run {run_id} is missing or already completed.")
                    return

                run["attempts"] = attempt
                save_state(state)
                action = run["action"]

            print(f"Running {action}, attempt {attempt}/3")
            env = os.environ.copy()
            env.update(load_env())
            env["INPUT_MODE"] = action
            env["ACTIONS_STEP_DEBUG"] = "false"

            result = subprocess.run(
                ["node", str(ROOT / "dist" / "index.js")],
                cwd=ROOT,
                env=env,
                check=False
            )

            with locked(STATE_LOCK):
                state = json.loads(STATE.read_text())
                run = next(item for item in state["runs"] if item["id"] == run_id)

                if state.get("date") != datetime.now(tz).date().isoformat():
                    print("Date changed during execution; not modifying new schedule.")
                    return

                if result.returncode == 0:
                    run["status"] = "done"
                    save_state(state)
                    print(f"Run {run_id} succeeded.")
                    notify(
                        f"✅ **Naukri update succeeded**\n"
                        f"Date: {state['date']}\n"
                        f"Action: {action}\n"
                        f"Scheduled time: {run['time']} IST\n"
                        f"Attempts: {attempt}"
                    )
                    return

                if attempt == 3:
                    run["status"] = "failed"
                    save_state(state)
                    print(f"Run {run_id} failed after three attempts.")
                    notify(
                        f"🚨 **Naukri update FAILED**\n"
                        f"Date: {state['date']}\n"
                        f"Action: {action}\n"
                        f"Scheduled time: {run['time']} IST\n"
                        f"Attempts: 3\n"
                        "Check scheduler/cron.log on the VM."
                    )
                    return

            notify(
                f"⚠️ **Naukri update attempt failed**\n"
                f"Action: {action}\n"
                f"Attempt: {attempt}/3\n"
                "Retrying in 10 minutes."
            )
            print("Update failed; retrying in 10 minutes.")
            time.sleep(600)



def run_update(run_id):
    # Scheduled jobs wait for any active manual or scheduled update.
    with locked(SDIR / ".update.lock"):
        _run_update(run_id)


def manual_update(action):
    """Run an immediate update, refusing to overlap another update."""
    if action not in {"headline", "resume", "both"}:
        return {"ok": False, "busy": False, "message": "Invalid action."}

    try:
        with locked(SDIR / ".update.lock", blocking=False):
            env = os.environ.copy()
            env.update(load_env())
            env["INPUT_MODE"] = action
            env["ACTIONS_STEP_DEBUG"] = "false"

            print(f"Starting manual Naukri update: {action}")
            result = subprocess.run(
                ["node", str(ROOT / "dist" / "index.js")],
                cwd=ROOT,
                env=env,
                check=False,
            )

            if result.returncode == 0:
                notify(f"⚡ Manual Naukri update succeeded\nAction: {action}")
                return {
                    "ok": True,
                    "busy": False,
                    "message": f"{action.title()} update completed successfully.",
                }

            notify(f"🚨 Manual Naukri update failed\nAction: {action}")
            return {
                "ok": False,
                "busy": False,
                "message": f"{action.title()} update failed. Check scheduler/cron.log.",
            }

    except BlockingIOError:
        return {
            "ok": False,
            "busy": True,
            "message": "Another Naukri update is running. Try again shortly.",
        }


def main():
    if len(sys.argv) < 2:
        raise ValueError("Usage: scheduler.py generate | run RUN_ID")

    if sys.argv[1] == "generate" and len(sys.argv) == 2:
        generate()
    elif sys.argv[1] == "generate" and sys.argv[2:] == ["--force"]:
        generate(force=True)
    elif sys.argv[1] == "run" and len(sys.argv) == 3:
        run_update(int(sys.argv[2]))
    else:
        raise ValueError("Usage: scheduler.py generate | run RUN_ID")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Scheduler error: {exc}", file=sys.stderr)
        notify(f"🚨 **Naukri scheduler error**\n{type(exc).__name__}: {exc}")
        sys.exit(1)
