"""Calendar deadlines and legacy page deadlines have separate meanings."""
from datetime import date
import re

from .util import SeedError, list_days


def calendar_date(value, *, optional=False):
    if optional and value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise SeedError("日期请填写 YYYY-MM-DD。")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise SeedError("这不是有效的日历日期。") from None
    return value


def page_date(pack, day):
    value = next((r["date"] for r in list_days(pack) if r["day"] == day), None)
    if value is None:
        return None
    return calendar_date(value)


def state(row, day, on):
    if row.get("due_on"):
        due = calendar_date(row["due_on"])
        current = calendar_date(on, optional=True)
        result = "unknown" if not current else "overdue" if current > due else "today" if current == due else "upcoming"
        return {"basis": "calendar", "due_on": due, "on": current, "state": result}
    due = row.get("due_day")
    result = "unscheduled" if due is None else "overdue" if day > due else "today" if day == due else "upcoming"
    return {"basis": "legacy_page" if due is not None else "none", "due_day": due, "state": result}
