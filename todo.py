"""Todoist CLI for Claude Code sessions and a Rainmeter desktop widget.

Token lives in Windows Credential Manager:  keyring  service "todoist", user "api".

  py todo.py brief [--folder NAME]    plan + closed in 3 days (+ all tasks of the section mapped to NAME), with ids
  py todo.py widget                   plan for the desktop, written to widget_file; also updates the journal
  py todo.py done [--days N]          what was closed (repeats included)
  py todo.py list [--section S] [--days N]
  py todo.py find TEXT
  py todo.py show ID                  content + description (vault pointer)
  py todo.py add "TEXT" --section S [--due "Oct 6"] [--parent ID] [--desc D] [--p 1|2|3, default 3]
  py todo.py close ID
"""
import argparse, json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import keyring
from todoist_api_python.api import TodoistAPI

from planner import Item, render, split_due

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
CACHE = HERE / "cache.json"
JOURNAL_STATE = HERE / "journal.json"
LABEL = "claude"
PRIORITY = {1: 4, 2: 3, 3: 2}  # P1 → API 4


def flat(pages):
    return [x for page in pages for x in page]


def token():
    return keyring.get_password("todoist", "api")


def api():
    return TodoistAPI(token())


def fetch(client):
    projects = {p.id: p.name for p in flat(client.get_projects())}
    sections = {s.id: s.name for s in flat(client.get_sections())}
    items = []
    for t in flat(client.get_tasks()):
        due, time = split_due(t.due.date if t.due else None)
        items.append(Item(t.id, t.content, projects.get(t.project_id, ""), sections.get(t.section_id, ""),
                          due, time, t.priority, t.parent_id, bool(t.due and t.due.is_recurring)))
    return items, projects


def load():
    """Live tasks, or the last snapshot with a warning. Never an empty plan that looks real."""
    try:
        items, projects = fetch(api())
        CACHE.write_text(json.dumps({"projects": projects, "items": [{**i.__dict__, "due": i.due and i.due.isoformat()}
                                    for i in items]}, ensure_ascii=False), encoding="utf-8")
        return items, projects, ""
    except Exception as e:
        if not CACHE.exists():
            return [], {}, f"⚠️ Todoist недоступний ({type(e).__name__}), знімка нема"
        raw = json.loads(CACHE.read_text(encoding="utf-8"))
        items = [Item(**{**r, "due": r["due"] and date.fromisoformat(r["due"])}) for r in raw["items"]]
        taken = datetime.fromtimestamp(CACHE.stat().st_mtime)
        return items, raw["projects"], f"⚠️ Todoist недоступний ({type(e).__name__}), знімок {taken:%d.%m %H:%M}"


def closed_events(days, projects):
    """Completions from the activity log. Unlike the completed-tasks list it also sees repeats (checked 04.10)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out, cursor = [], None
    with httpx.Client(headers={"Authorization": f"Bearer {token()}"}, timeout=20) as http:
        for _ in range(5):
            params = {"event_type": "completed", "limit": 100, **({"cursor": cursor} if cursor else {})}
            r = http.get("https://api.todoist.com/api/v1/activities", params=params)
            r.raise_for_status()
            page = r.json()
            for e in page.get("results", []):
                at = datetime.fromisoformat(e["event_date"].replace("Z", "+00:00")).astimezone()
                if at < since:
                    return out
                out.append({"id": e["id"], "at": at.isoformat(timespec="minutes"),
                            "content": (e.get("extra_data") or {}).get("content", ""),
                            "project": projects.get(e.get("parent_project_id"), "")})
            cursor = page.get("next_cursor")
            if not cursor:
                break
    return out


def update_journal(events):
    """Append new completions to the vault journal. Rebuilt from journal.json, so it never duplicates.
    Returns all journaled events: events removed from it by hand (tests) stay out everywhere."""
    state = json.loads(JOURNAL_STATE.read_text(encoding="utf-8")) if JOURNAL_STATE.exists() else {"seen": [], "events": []}
    new = [e for e in events if e["id"] not in state["seen"]]
    if new:
        state["seen"] += [e["id"] for e in new]
        state["events"] += new
        write_journal(state)
    return state["events"]


def write_journal(state):
    JOURNAL_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    out = ["# Todoist: журнал закритого", "",
           "_Пише `todo.py` сам на кожному циклі віджета. Руками не правити: файл перебудовується з `journal.json`._",
           "_На старті сесії Claude звіряє свіже з vault і памʼяттю._", ""]
    day = None
    for e in sorted(state["events"], key=lambda e: e["at"], reverse=True):
        at = datetime.fromisoformat(e["at"])
        if at.date() != day:
            day = at.date()
            out += ["", f"## {['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'нд'][day.weekday()]} {day:%d.%m.%Y}"]
        out.append(f"- {at:%H:%M} {e['content']}" + (f" · {e['project']}" if e["project"] else ""))
    Path(CFG["journal_file"]).write_text("\n".join(out) + "\n", encoding="utf-8")


def closed_block(events, today):
    by_day = {}
    for e in events:
        if e["project"] not in CFG["exclude"]:
            by_day.setdefault(datetime.fromisoformat(e["at"]).date(), []).append(e["content"])
    if not by_day:
        return ["✅ ЗАКРИТО за 3 дні: нічого"]
    return ["✅ ЗАКРИТО за 3 дні (звір з vault):"] + [
        f"  {'сьогодні' if d == today else f'{d:%d.%m}'}: " + " · ".join(c[:40] for c in cs)
        for d, cs in sorted(by_day.items(), reverse=True)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("brief"); p.add_argument("--folder", default="")
    sub.add_parser("widget")
    p = sub.add_parser("done"); p.add_argument("--days", type=int, default=3)
    p = sub.add_parser("list"); p.add_argument("--section"); p.add_argument("--days", type=int, default=3)
    p = sub.add_parser("find"); p.add_argument("text")
    p = sub.add_parser("show"); p.add_argument("id")
    p = sub.add_parser("add"); p.add_argument("content"); p.add_argument("--section", required=True)
    p.add_argument("--due"); p.add_argument("--parent"); p.add_argument("--desc")
    p.add_argument("--p", type=int, choices=[1, 2, 3], default=3)  # every task gets a flag
    p = sub.add_parser("close"); p.add_argument("id")
    a = ap.parse_args()
    today, now = date.today(), datetime.now()

    if a.cmd in ("brief", "widget", "done", "list"):
        items, projects, warn = load()
        items = [i for i in items if i.project not in CFG["exclude"]]
        events, ev_warn = [], ""
        if a.cmd != "list" and not warn:
            try:
                days = getattr(a, "days", 3)
                since = (datetime.now() - timedelta(days=days)).astimezone()
                events = [e for e in update_journal(closed_events(days, projects))
                          if datetime.fromisoformat(e["at"]) >= since]
            except Exception as e:
                ev_warn = f"⚠️ журнал закритого недоступний ({type(e).__name__})"
        if a.cmd == "widget":
            done_today = None if ev_warn or warn else sum(datetime.fromisoformat(e["at"]).date() == today for e in events)
            text = render(items, today, now, warning=warn or ev_warn, work_project=CFG["work_project"], closed_today=done_today)
            (HERE / CFG["widget_file"]).write_text(text, encoding="utf-16")
        elif a.cmd == "done":
            print("\n".join(closed_block(events, today)) if not ev_warn else ev_warn)
        elif a.cmd == "list":
            if a.section:
                items = [i for i in items if a.section.lower() in i.section.lower()]
            print(render(items, today, now, days=a.days, with_ids=True, warning=warn))
        else:  # closed + section first: the brief budget cuts from the tail, far days are cheapest to lose
            print("\n".join(closed_block(events, today)) if not (ev_warn or warn) else ev_warn or "")
            section = CFG["sections"].get(a.folder)
            if section:
                later = [i for i in items if i.section == section and not i.parent_id
                         and (not i.due or i.due > today + timedelta(days=3))]
                print(f"📂 СЕКЦІЯ «{section}» (сесія про {a.folder}), далі за 3 дні:")
                print("\n".join(f"  · {i.content[:50]} · {i.due:%d.%m} `{i.id}`" if i.due else f"  · {i.content[:50]} · без дати `{i.id}`"
                                for i in sorted(later, key=lambda i: i.due or date.max)) or "  нічого")
            print(render(items, today, now, with_ids=True, warning=warn, work_project=CFG["work_project"]))
        return

    client = api()
    if a.cmd == "find":
        for i in fetch(client)[0]:
            if a.text.lower() in i.content.lower():
                print(f"`{i.id}` {i.content} · {i.section or i.project} · {i.due or 'без дати'}")
    elif a.cmd == "show":
        t = client.get_task(a.id)
        print(t.content, "\n", t.description, sep="")
    elif a.cmd == "add":
        matches = [s for s in flat(client.get_sections()) if a.section.lower() in s.name.lower()]
        if len(matches) != 1:
            sys.exit(f"секція «{a.section}»: збігів {len(matches)}, треба рівно 1")
        kw = dict(labels=[LABEL], description=a.desc, due_string=a.due,
                  due_lang="en" if a.due else None, priority=PRIORITY.get(a.p))
        kw.update(parent_id=a.parent) if a.parent else kw.update(section_id=matches[0].id, project_id=matches[0].project_id)
        # Todoist cuts "@word" out of the title as a label even with auto_parse_labels=False (checked 04.10)
        t = client.add_task(a.content.replace("@", ""), **{k: v for k, v in kw.items() if v is not None})
        note = " (@ прибрано, інакше Todoist ріже слово)" if "@" in a.content else ""
        print(f"створено `{t.id}` {t.content} · {t.due.date if t.due else 'без дати'}{note}")
    elif a.cmd == "close":
        t = client.get_task(a.id)
        client.complete_task(a.id)
        print(f"закрито: {t.content}")


if __name__ == "__main__":
    main()
