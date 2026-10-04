# todoist-plan

**English** | [Українська](README.uk.md)

A day plan that lives in Todoist and shows up in two places: on the Windows desktop (Rainmeter widget)
and at the start of every Claude Code session (a short brief). Built for one person who kept asking
"what's the plan for today?" instead of just doing it.

**Todoist holds "what and when". Notes hold "why and how".** Each task description points to the note
section with the context, so the plan stays short and nothing is lost.

## What you get

```
ESSENTIALS: Pay internet (−2 d) · Exercise · English     ← personal tasks folded into one line
TODAY
◐ Client session · 3 more                                ← ● P1  ◐ P2  ○ P3, "3 more" = open subtasks
   ↳ 19:20 Send the follow-up
TUE 06.10
● Test 10 applications (Bot v1)
closed today: 2 · no date: 4 · updated 08:00             ← closed today, undated, last refresh
```

Labels come in English (`"lang": "en"`) or Ukrainian (`"lang": "uk"`), set in `config.json`. Task names stay as you wrote them.

- **Overdue + today + 3 days.** Repeating tasks count as overdue too: a missed bill is still missed.
- **Work in detail, personal in one line**, so habits and errands are seen but do not push work down.
- **Closed log.** Every widget refresh appends new completions to a Markdown journal in your notes,
  so the notes know what was done even if nobody opened them for a week.
- **Never an empty plan that looks real.** Offline or token problems show the last snapshot with a ⚠️ line.

## Setup (Windows, ~15 min)

```
py -m pip install todoist-api-python keyring httpx
copy config.example.json config.json            # set language, work project, excluded projects, journal path
py save_token.py                                # after copying the API token in Todoist
py todo.py brief
```

**Widget:** install [Rainmeter](https://github.com/rainmeter/rainmeter/releases), then
- copy `rainmeter/PlanDay/@Resources/paths.example.inc` to `paths.inc` and set the three paths;
- link the skin: `New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\Rainmeter\Skins\PlanDay" -Target .\rainmeter\PlanDay`;
- load it: `Rainmeter.exe !ActivateConfig "PlanDay" "PlanDay.ini"`, then `!ZPos "-2" "PlanDay"` so it sits on the
  desktop and **Win+D** shows it instantly;
- optional hotkey: a Start Menu shortcut to `Rainmeter.exe !ToggleConfig "PlanDay" "PlanDay.ini"` with a Shortcut key
  (Windows handles these with a 1-5 s delay).

The skin runs `todo.py widget` on load and every 5 minutes (about 36 API calls an hour, the limit is 1000 per 15 minutes).
Clicking it opens the Todoist app on Today.

## Commands

| | |
|---|---|
| `todo.py brief [--folder NAME]` | plan + closed in 3 days (+ every task of the section mapped to NAME), with ids |
| `todo.py widget` | writes `widget.txt` for the skin and updates the journal |
| `todo.py done [--days N]` | what was closed, repeats included |
| `todo.py list [--section S] [--days N]` / `find TEXT` / `show ID` | look around |
| `todo.py add "TEXT" --section S [--due "Oct 6"] [--parent ID] [--p 1-3]` | new task, label `claude`, P3 by default |
| `todo.py close ID` | close |

## Todoist API traps we hit (Oct 2026, API v1, SDK 4.0)

1. **Deadlines are Pro only**: `deadline_date` on Free returns 403 `PREMIUM_ONLY`.
2. **`@word` in a title is cut out** as a label even with `auto_parse_labels=False`. `add` drops the `@` sign.
3. **A closed subtask stays closed** when its repeating parent moves to the next date, so checklists under repeats work once.
4. **Fixed-timezone dues come back in UTC**: "31 Oct 00:00 Europe/Warsaw" arrives as 30 Oct 23:00. `split_due` shifts it.
5. **Repeats are invisible to the completed-tasks endpoint** (they move, not close). The activity log sees them,
   a few seconds late.
6. **`TodoistAPI(token)` without a variable** closes its HTTP client before the first page is fetched.

## Tests

`py -m unittest discover -s tests`. Planning and rendering are pure functions with synthetic tasks, no network.

MIT license.
