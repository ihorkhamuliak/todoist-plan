"""Planning logic: which tasks to show and how. No network here, so all of it is unit-tested."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

BULLET = {4: "●", 3: "◐", 2: "○"}  # Todoist API scale: 4 = P1 (red)

# Every word the widget, the brief, the journal and the CLI show. "lang" in config.json picks one.
TEXT = {
    "uk": dict(days=["пн", "вт", "ср", "чт", "пт", "сб", "нд"], today="СЬОГОДНІ", overdue="ПРОСТРОЧЕНЕ", basic="БАЗОВЕ",
               more="ще {n}", late="−{n} дн", closed_today="закрито сьогодні: {n}", undated="без дати: {n}",
               updated="оновлено {t}", today_word="сьогодні", nothing="нічого", no_date="без дати",
               closed_none="✅ ЗАКРИТО за 3 дні: нічого", closed_head="✅ ЗАКРИТО за 3 дні (звір з vault):",
               offline="⚠️ Todoist недоступний ({e}), знімок {t}", offline_none="⚠️ Todoist недоступний ({e}), знімка нема",
               journal_off="⚠️ журнал закритого недоступний ({e})",
               journal=["# Todoist: журнал закритого", "",
                        "_Пише `todo.py` сам на кожному циклі віджета. Руками не правити: файл перебудовується з `journal.json`._",
                        "_На старті сесії Claude звіряє свіже з vault і памʼяттю._", ""],
               section="📂 СЕКЦІЯ «{s}» (сесія про {f}), далі за 3 дні:",
               section_bad="секція «{s}»: збігів {n}, треба рівно 1", at_removed=" (@ прибрано, інакше Todoist ріже слово)",
               created="створено `{id}` {c} · {d}", closed="закрито: {c}"),
    "en": dict(days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"], today="TODAY", overdue="OVERDUE", basic="ESSENTIALS",
               more="{n} more", late="−{n} d", closed_today="closed today: {n}", undated="no date: {n}",
               updated="updated {t}", today_word="today", nothing="nothing", no_date="no date",
               closed_none="✅ CLOSED in 3 days: nothing", closed_head="✅ CLOSED in 3 days (check against notes):",
               offline="⚠️ Todoist unavailable ({e}), snapshot {t}", offline_none="⚠️ Todoist unavailable ({e}), no snapshot",
               journal_off="⚠️ closed-task journal unavailable ({e})",
               journal=["# Todoist: closed-task journal", "",
                        "_Written by `todo.py` on every widget refresh. Do not edit by hand: rebuilt from `journal.json`._",
                        "_At session start Claude checks the fresh entries against the notes._", ""],
               section="📂 SECTION «{s}» (session about {f}), beyond 3 days:",
               section_bad="section «{s}»: {n} matches, need exactly 1", at_removed=" (@ removed, Todoist would cut the word)",
               created="created `{id}` {c} · {d}", closed="closed: {c}"),
}


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


def _day_name(d, today, t):
    return t["today"] if d == today else f"{t['days'][d.weekday()].upper()} {d:%d.%m}"


def _lines(group, by_id, kids, with_ids, t):
    """Subtasks go under their parent when it is in the same group, otherwise they carry its name."""
    shown = {i.id for i in group}
    out = []

    def text(i, standalone):
        s = i.content
        if standalone and i.parent_id in by_id:
            s += f" ({by_id[i.parent_id].content})"
        if kids.get(i.id):
            s += " · " + t["more"].format(n=kids[i.id])
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


def render(items, today, now, days=3, with_ids=False, warning="", work_project=None, closed_today=None, lang="uk"):
    """Plain text for the widget (with_ids=False) or markdown-ish for the session brief (with_ids=True).
    With work_project set, personal tasks fold into one "basic" line under each day's header (overdue ones join
    today's line, first), so they are not forgotten and do not push work tasks down."""
    t = TEXT[lang]
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
    if overdue:
        out.append(t["overdue"])
        out += [f"{_lines([i], by_id, kids, with_ids, t)[0]} · {t['late'].format(n=(today - i.due).days)}" for i in overdue]
    basic.sort(key=lambda i: (i.due, -i.priority))
    for d, group in by_day.items():
        personal = basic if d == today else [i for i in group if work_project and i.project != work_project]
        if group or personal:
            out.append(_day_name(d, today, t))
            if personal:
                out.append(f"{t['basic']}: " + " · ".join(
                    _short(i.content) + (f" ({t['late'].format(n=(today - i.due).days)})" if i.due < today else "")
                    for i in personal))
            out += _lines([i for i in group if i not in personal], by_id, kids, with_ids, t)
    closed = t["closed_today"].format(n=closed_today) + " · " if closed_today is not None else ""
    out.append(f"{closed}{t['undated'].format(n=undated)} · {t['updated'].format(t=f'{now:%H:%M}')}")
    return "\n".join(out)
