"""
Pluto reminder daemon — runs at Windows startup, independent of the Tauri app.

Polls the SQLite database every 60 seconds and fires Windows toast notifications
for any reminders (and calendar events) that are due within the next 15 minutes.

Usage:
    pythonw reminder_daemon.py        # silent background (no console window)
    python  reminder_daemon.py        # with console, useful for debugging

Dependencies (install once):
    pip install winotify schedule
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate config.json relative to this file (project root / backend/)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "backend" / "config.json"


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _db_path() -> str:
    cfg = _load_config()
    raw = cfg["memory"]["db_path"]
    if os.path.isabs(raw):
        return raw
    return str(ROOT / "backend" / raw)


# ---------------------------------------------------------------------------
# SQLite helpers (no FastAPI / helpers package dependency)
# ---------------------------------------------------------------------------

def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_naive_utc(iso: str) -> datetime:
    """Parse any ISO-8601 string to a naive UTC datetime."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None) - dt.utcoffset()
    return dt


def _get_due_reminders(db_path: str, window_minutes: int = 15) -> list[dict]:
    """Return reminders due within the next window_minutes that haven't been notified yet."""
    now = datetime.utcnow()  # naive UTC
    until = now + timedelta(minutes=window_minutes)

    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT id, title, remind_at, recurrence, notified_at FROM reminders"
    ).fetchall()
    conn.close()

    due: list[dict] = []
    for row in rows:
        r = dict(row)
        try:
            remind_dt = _parse_naive_utc(r["remind_at"])
        except ValueError:
            continue

        recurrence = r.get("recurrence") or ""

        if recurrence:
            step = _recurrence_step(recurrence)
            while remind_dt < now - timedelta(minutes=window_minutes):
                remind_dt += step
            if now <= remind_dt <= until:
                notified_at = r.get("notified_at")
                if notified_at:
                    try:
                        notified_dt = _parse_naive_utc(notified_at)
                        if (now - notified_dt) < step:
                            continue
                    except ValueError:
                        pass
                r["remind_at"] = remind_dt.isoformat()
                due.append(r)
        else:
            # Fire if past due and not yet notified (generous: up to 60 min late)
            if remind_dt <= until and remind_dt >= now - timedelta(minutes=60) and not r.get("notified_at"):
                due.append(r)

    return due


def _get_due_events(db_path: str, window_minutes: int = 15) -> list[dict]:
    """Return calendar events starting within the next window_minutes, unnotified."""
    now = datetime.utcnow()  # naive UTC
    until = now + timedelta(minutes=window_minutes)

    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT id, title, start_time, end_time, recurrence FROM events"
    ).fetchall()
    conn.close()

    due: list[dict] = []
    for row in rows:
        e = dict(row)
        try:
            start_dt = _parse_naive_utc(e["start_time"])
        except ValueError:
            continue

        recurrence = e.get("recurrence") or ""

        if recurrence:
            step = _recurrence_step(recurrence)
            while start_dt < now - timedelta(minutes=window_minutes):
                start_dt += step
            if now <= start_dt <= until:
                e["start_time"] = start_dt.isoformat()
                due.append(e)
        else:
            if now <= start_dt <= until:
                due.append(e)

    return due


def _mark_reminder_notified(db_path: str, reminder_id: int) -> None:
    now = datetime.utcnow().isoformat()
    conn = _connect(db_path)
    conn.execute("UPDATE reminders SET notified_at = ? WHERE id = ?", (now, reminder_id))
    conn.commit()
    conn.close()


def _recurrence_step(recurrence: str) -> timedelta:
    if recurrence == "daily":
        return timedelta(days=1)
    if recurrence == "weekly":
        return timedelta(weeks=1)
    if recurrence == "monthly":
        return timedelta(days=30)
    return timedelta(weeks=1)


# ---------------------------------------------------------------------------
# Notification (winotify)
# ---------------------------------------------------------------------------

def _notify(title: str, message: str) -> None:
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="Pluto",
            title=title,
            msg=message,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        # Fallback: print to stdout (visible when running with python, not pythonw)
        print(f"[REMINDER] {title}: {message}", flush=True)
    except Exception as exc:
        print(f"[REMINDER ERROR] {exc}", flush=True)


# ---------------------------------------------------------------------------
# Already-notified cache (prevents duplicate toasts within the same process)
# ---------------------------------------------------------------------------

_notified_events: set[str] = set()  # "event-{id}-{date}" keys


def _event_key(event_id: int, start_time: str) -> str:
    # Use just the date portion so daily/weekly events re-fire next cycle
    date_part = start_time[:10]
    return f"event-{event_id}-{date_part}"


# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

def _poll(db_path: str) -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Reminders ---
    try:
        for r in _get_due_reminders(db_path):
            _notify("Pluto Reminder", r["title"])
            _mark_reminder_notified(db_path, r["id"])
    except Exception as exc:
        print(f"[ERROR] reminders poll: {exc}", flush=True)

    # --- Calendar events ---
    try:
        for e in _get_due_events(db_path):
            key = _event_key(e["id"], e["start_time"])
            if key in _notified_events:
                continue
            _notified_events.add(key)
            end_str = ""
            if e.get("end_time"):
                try:
                    end_dt = datetime.fromisoformat(e["end_time"].replace("Z", "+00:00"))
                    # Display in local terms — keep simple
                    end_str = f" – {end_dt.strftime('%H:%M')} UTC"
                except ValueError:
                    pass
            start_dt = datetime.fromisoformat(e["start_time"].replace("Z", "+00:00"))
            msg = f"Starting at {start_dt.strftime('%H:%M')} UTC{end_str}"
            _notify(f"Pluto: {e['title']}", msg)
    except Exception as exc:
        print(f"[ERROR] events poll: {exc}", flush=True)


def main() -> None:
    print("Pluto reminder daemon starting...", flush=True)

    try:
        db_path = _db_path()
    except Exception as exc:
        print(f"[FATAL] Could not load config: {exc}", flush=True)
        sys.exit(1)

    print(f"Database: {db_path}", flush=True)
    print("Polling every 60 seconds. Press Ctrl+C to stop.", flush=True)

    while True:
        try:
            _poll(db_path)
        except Exception as exc:
            print(f"[ERROR] poll cycle: {exc}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
