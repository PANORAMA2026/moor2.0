"""Persistent monthly itinerary lifecycle management.

The uploaded calendar is stored locally with explicit month metadata. It remains
available throughout that calendar month and is marked for replacement once the
month has ended.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os

import pandas as pd

from config.constants import DB_FILE_PATH

CALENDAR_STORAGE_PATH = os.path.join(os.path.dirname(DB_FILE_PATH), "saved_schedule.parquet")
CALENDAR_META_PATH = os.path.join(os.path.dirname(DB_FILE_PATH), "saved_schedule_meta.json")


def _meta_default() -> dict:
    return {"calendar_month": None, "uploaded_at_utc": None, "source_name": None}


def load_calendar_meta() -> dict:
    if not os.path.exists(CALENDAR_META_PATH):
        return _meta_default()
    try:
        with open(CALENDAR_META_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        base = _meta_default()
        base.update(data if isinstance(data, dict) else {})
        return base
    except Exception:
        return _meta_default()


def save_calendar_meta(calendar_month: str, source_name: str | None = None) -> None:
    data = {
        "calendar_month": calendar_month,
        "uploaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_name": source_name,
    }
    os.makedirs(os.path.dirname(CALENDAR_META_PATH), exist_ok=True)
    with open(CALENDAR_META_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def clear_calendar_storage() -> None:
    for path in (CALENDAR_STORAGE_PATH, CALENDAR_META_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def calendar_month_from_schedule(schedule: pd.DataFrame) -> str | None:
    if schedule is None or schedule.empty:
        return None
    dates = pd.to_datetime(schedule.get("ETA"), errors="coerce").dropna()
    if dates.empty:
        return None
    # Monthly files are expected to represent one operational month. Use the
    # first valid ETA as the month key and validate consistency at upload time.
    return dates.iloc[0].strftime("%Y-%m")


def schedule_months(schedule: pd.DataFrame) -> set[str]:
    if schedule is None or schedule.empty:
        return set()
    dates = pd.to_datetime(schedule.get("ETA"), errors="coerce").dropna()
    return set(dates.dt.strftime("%Y-%m").tolist())


def load_persisted_calendar() -> pd.DataFrame:
    if not os.path.exists(CALENDAR_STORAGE_PATH):
        return pd.DataFrame()
    try:
        return pd.read_parquet(CALENDAR_STORAGE_PATH)
    except Exception:
        return pd.DataFrame()


def persist_calendar(schedule: pd.DataFrame, source_name: str | None = None) -> str:
    month_set = schedule_months(schedule)
    if not month_set:
        raise ValueError("Il calendario non contiene ETA valide.")
    if len(month_set) != 1:
        months = ", ".join(sorted(month_set))
        raise ValueError(
            f"Il file contiene piu mesi ({months}). Caricare un calendario mensile separato."
        )
    month = next(iter(month_set))
    schedule.to_parquet(CALENDAR_STORAGE_PATH, index=False)
    save_calendar_meta(month, source_name)
    return month


def month_completed(calendar_month: str | None, now: datetime | None = None) -> bool:
    if not calendar_month:
        return False
    try:
        year, month = [int(x) for x in calendar_month.split("-")]
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return (current.year, current.month) > (year, month)
    except Exception:
        return False


def calendar_state(now: datetime | None = None) -> dict:
    meta = load_calendar_meta()
    schedule = load_persisted_calendar()
    completed = month_completed(meta.get("calendar_month"), now)
    return {
        "schedule": schedule,
        "meta": meta,
        "calendar_month": meta.get("calendar_month"),
        "completed": completed,
        "needs_next_month": completed or schedule.empty,
    }
