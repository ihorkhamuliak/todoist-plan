"""Planning logic: which tasks to show and how. No network here, so all of it is unit-tested."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
BULLET = {4: "●", 3: "◐", 2: "○"}  # Todoist API scale: 4 = P1 (red)


@dataclass
class Item:
    id: str
    content: str
    project: str
    section: str = ""
    due: date | None = None
    time: str = ""  # "19:20" when the due has a time
    priority: int = 1
    parent_id: str | None = None
    recurring: bool = False


def split_due(value, tz=None):
    """Todoist due → (local date, "HH:MM" or ""). Fixed-timezone dues arrive in UTC and are shifted to tz."""
    if not isinstance(value, datetime):
        return value, ""
    if value.tzinfo:
        value = value.astimezone(tz)
    return value.date(), value.strftime("%H:%M")


def plan(items, today, days=3):
    """→ (overdue, {day: [items]} for today..today+days, undated top-level count)."""
    end = today + timedelta(days=days)
    overdue = [i for i in items if i.due and i.due < today]  # repeats too: a missed bill is still missed
    by_day = {today + timedelta(n): [] for n in range(days + 1)}
    for i in items:
        if i.due and today <= i.due <= end:
            by_day[i.due].append(i)
    key = lambda i: (-i.priority, i.time or "99:99", i.content)
    overdue.sort(key=lambda i: (i.due, *key(i)))
    for day in by_day.values():
        day.sort(key=key)
    undated = sum(1 for i in items if not i.due and not i.parent_id)
    return overdue, by_day, undated


def _day_name(d, today):
    return "СЬОГОДНІ" if d == today else f"{WD[d.weekday()].upper()} {d:%d.%m}"


def _lines(group, by_id, kids, with_ids):
    """Subtasks go under their parent when it is in the same group, otherwise they carry its name."""
    shown = {i.id for i in group}
    out = []

    def text(i, standalone):
        s = i.content
        if standalone and i.parent_id in by_id:
            s += f" ({by_id[i.parent_id].content})"
        if kids.get(i.id):
            s += f" · ще {kids[i.id]}"
        if i.time:
            s = f"{i.time} {s}"
        if with_ids:
            s += f" `{i.id}`"
        return s

    for i in group:
        if i.parent_id in shown:
            continue
        out.append(f"{BULLET.get(i.priority, '·')} {text(i, True)}")
        out += [f"   ↳ {text(c, False)}" for c in group if c.parent_id == i.id]
    return out


def _short(text, n=30):
    return text if len(text) <= n else text[:n].rstrip() + "…"


def render(items, today, now, days=3, with_ids=False, warning="", work_project=None, closed_today=None):
    """Plain text for the widget (with_ids=False) or markdown-ish for the session brief (with_ids=True).
    With work_project set, personal tasks due today or overdue fold into one "БАЗОВЕ" line on top,
    so they are not forgotten and do not push work tasks down."""
    by_id = {i.id: i for i in items}
    kids = {}
    for i in items:
        if i.parent_id:
            kids[i.parent_id] = kids.get(i.parent_id, 0) + 1
    basic = []
    if work_project:
        basic = [i for i in items if i.project != work_project and i.due and i.due <= today]
        items = [i for i in items if i not in basic]
    overdue, by_day, undated = plan(items, today, days)

    out = [warning] if warning else []
    if basic:
        basic.sort(key=lambda i: (i.due, -i.priority))
        out.append("БАЗОВЕ: " + " · ".join(
            _short(i.content) + (f" (−{(today - i.due).days} дн)" if i.due < today else "") for i in basic))
    if overdue:
        out.append("ПРОСТРОЧЕНЕ")
        out += [f"{_lines([i], by_id, kids, with_ids)[0]} · −{(today - i.due).days} дн" for i in overdue]
    for d, group in by_day.items():
        if group:
            out.append(_day_name(d, today))
            personal = [i for i in group if work_project and i.project != work_project]
            if personal:
                out.append("БАЗОВЕ: " + " · ".join(_short(i.content) for i in personal))
            out += _lines([i for i in group if i not in personal], by_id, kids, with_ids)
    closed = f"закрито сьогодні: {closed_today} · " if closed_today is not None else ""
    out.append(f"{closed}без дати: {undated} · оновлено {now:%H:%M}")
    return "\n".join(out)
