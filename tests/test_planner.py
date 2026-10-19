import sys, unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import timezone, timedelta
from planner import Item, overload, plan, render, split_due

SUN = date(2026, 10, 4)
NOW = datetime(2026, 10, 4, 21, 40)


def d(day):
    return date(2026, 10, day)


class Plan(unittest.TestCase):
    def test_recurring_task_past_due_is_overdue(self):
        # a monthly bill that was not done on the 1st must not hide just because it repeats
        bills = Item("1", "Count monthly spending", "Home", due=d(1), recurring=True)
        overdue, _, _ = plan([bills], SUN)
        self.assertEqual([i.id for i in overdue], ["1"])

    def test_window_is_today_plus_three_days(self):
        items = [Item(str(n), f"t{n}", "Work", due=d(n)) for n in (4, 7, 8)]
        _, by_day, _ = plan(items, SUN)
        shown = [i.id for day in by_day.values() for i in day]
        self.assertEqual(shown, ["4", "7"])

    def test_undated_counts_only_top_level(self):
        items = [Item("a", "idea", "Work"), Item("b", "step", "Work", parent_id="a")]
        self.assertEqual(plan(items, SUN)[2], 1)

    def test_day_sorted_by_priority_then_time(self):
        items = [Item("low", "low", "W", due=d(5), time="09:00"),
                 Item("p1", "p1", "W", due=d(5), priority=4),
                 Item("late", "late", "W", due=d(5), time="19:20")]
        _, by_day, _ = plan(items, SUN)
        self.assertEqual([i.id for i in by_day[d(5)]], ["p1", "low", "late"])


class SplitDue(unittest.TestCase):
    def test_fixed_timezone_due_comes_in_utc_and_must_be_shifted(self):
        # Todoist returns "31 Oct 00:00 Europe/Warsaw" as 30 Oct 23:00 UTC: a day early if taken as is
        utc = datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(split_due(utc, tz=timezone(timedelta(hours=1))), (d(31), "00:00"))

    def test_floating_time_and_plain_date_stay(self):
        self.assertEqual(split_due(datetime(2026, 10, 5, 19, 20)), (d(5), "19:20"))
        self.assertEqual(split_due(d(5)), (d(5), ""))
        self.assertEqual(split_due(None), (None, ""))


class Render(unittest.TestCase):
    def test_overdue_shows_days_late(self):
        text = render([Item("1", "Pay bills", "Home", due=d(1), recurring=True)], SUN, NOW)
        self.assertIn("ПРОСТРОЧЕНЕ\n· Pay bills · −3 дн", text)

    def test_subtask_sits_under_parent_same_day(self):
        items = [Item("p", "Outreach", "W", due=d(5), priority=3),
                 Item("c", "DM a lead", "W", due=d(5), time="19:20", parent_id="p"),
                 Item("c2", "Ping MD", "W", parent_id="p")]
        text = render(items, SUN, NOW)
        self.assertIn("ПН 05.10\n◐ Outreach · ще 2\n   ↳ 19:20 DM a lead", text)

    def test_subtask_without_parent_in_group_names_parent(self):
        items = [Item("p", "Bot v1", "W", due=d(11)),
                 Item("c", "Test 10 applications", "W", due=d(6), parent_id="p")]
        self.assertIn("· Test 10 applications (Bot v1)", render(items, SUN, NOW))

    def test_brief_mode_has_ids(self):
        text = render([Item("42", "Widget", "W", section="System", due=SUN)], SUN, NOW, with_ids=True)
        self.assertIn("СЬОГОДНІ\n· Widget `42`", text)

    def test_personal_today_and_overdue_fold_into_basic_line_under_today(self):
        items = [Item("w", "Client session", "Work", due=SUN),
                 Item("h", "Morning exercise, yoga and a cold shower", "Habits", due=SUN, recurring=True),
                 Item("b", "Pay internet", "Home", due=d(2)),
                 Item("f", "Birthday", "Home", due=d(6))]
        text = render(items, SUN, NOW, work_project="Work")
        self.assertEqual(text.split("\n")[:3], [
            "СЬОГОДНІ", "БАЗОВЕ: Pay internet (−2 дн) · Morning exercise, yoga and a c…", "· Client session"])
        self.assertNotIn("ПРОСТРОЧЕНЕ", text)       # personal overdue lives in the basic line
        self.assertIn("ВТ 06.10\nБАЗОВЕ: Birthday", text)  # future days fold personal tasks too

    def test_day_with_only_personal_tasks_still_shows(self):
        text = render([Item("h", "Gym", "Habits", due=d(5))], SUN, NOW, work_project="Work")
        self.assertIn("ПН 05.10\nБАЗОВЕ: Gym", text)

    def test_only_overdue_personal_still_opens_today(self):
        text = render([Item("h", "Gym", "Habits", due=d(3))], SUN, NOW, work_project="Work")
        self.assertTrue(text.startswith("СЬОГОДНІ\nБАЗОВЕ: Gym (−1 дн)\n"))

    def test_footer_counts_closed_today(self):
        self.assertTrue(render([], SUN, NOW, closed_today=4).endswith("закрито сьогодні: 4 · без дати: 0 · оновлено 21:40"))

    def test_english_labels(self):
        items = [Item("w", "Client session", "Work", due=SUN, priority=3),
                 Item("h", "Gym", "Habits", due=d(2)),
                 Item("o", "Report", "Work", due=d(3), priority=4)]
        text = render(items, SUN, NOW, work_project="Work", closed_today=1, lang="en")
        self.assertEqual(text.split("\n"), [
            "OVERDUE", "● Report · −1 d", "TODAY", "ESSENTIALS: Gym (−2 d)", "◐ Client session",
            "closed today: 1 · no date: 0 · updated 21:40"])

    def test_warning_goes_first(self):
        text = render([], SUN, NOW, warning="⚠️ Todoist offline")
        self.assertTrue(text.startswith("⚠️ Todoist offline\n"))
        self.assertTrue(text.endswith("без дати: 0 · оновлено 21:40"))


# Made-up tasks shaped like a real overloaded day: several sessions planned it and nobody added it up.
# SQL comes from two sections (job prep + learning); Acme is one project's focus in its own section.
JOB, LEARN, CLIENTS, SOCIAL = "Job", "Learning", "Clients", "Social"
TUE = [("Acme тест: Ollama на ноут + перший виклик моделі (з Python або n8n), ~1,5 год", JOB),
       ("Acme тест: SQL GROUP BY + Excel зведена і XLOOKUP сам на час, ~1,5 год", JOB),
       ("Acme тест: відповідь рекрутера → доробити міні-сервіс + README + пробний тест 1 год на час", JOB),
       ("Acme тест: міні-сервіс у n8n (лист → тема і мова JSON від Ollama → маршрут), ~3 год", JOB),
       ("Бот клієнта: постів за добу проти медіани, 5 хв", CLIENTS),
       ("1) Поняття вголос: черга, ETL, REST, OAuth; ~30 хв перед Ollama", LEARN),
       ("15 хв LinkedIn: відповіді під своїм + 3-5 коментарів", SOCIAL),
       ("SQL етап 1 → вихід", LEARN), ("SQL зранку: розминка + урок", LEARN),
       ("Бот клієнта: усі канали постять, 2 хв", CLIENTS),
       ("Свій бот: перший дайджест на новій моделі, 2 хв", JOB),
       ("Переглянути контент автора і, можливо, придумати рубрику", SOCIAL)]


class Overload(unittest.TestCase):
    def day(self, tasks, project="Work"):
        return [Item(str(n), c, project, section=s, due=d(20)) for n, (c, s) in enumerate(tasks)]

    def test_real_overloaded_tuesday_is_flagged_by_the_cross_section_repeat(self):
        items = self.day(TUE) + [Item("e", "Англійська", "Habits", due=d(20))]  # personal: not counted
        flags = overload(items, d(19), work_project="Work", lang="uk")
        self.assertEqual(list(flags), [d(20)])
        self.assertIn("SQL ×3", flags[d(20)])           # job section + learning section: planned twice
        self.assertNotIn("Acme", flags[d(20)])          # four Acme tasks in its own section = a focus day
        # estimates alone miss this day: 1.5+1.5+1+3 h + 54 min = 7.9 h < 8, and 3 tasks carry no estimate
        self.assertIn("~7,9 год за оцінками, 3 без оцінки", flags[d(20)])

    def test_replanned_tuesday_is_quiet(self):
        # the same day replanned: the service moves to the test date, one SQL block, checks of 2-15 min stay
        keep = [t for t in TUE if "міні-сервіс" not in t[0] and not t[0].startswith(("SQL", "Переглянути"))]
        keep.append(("SQL зранку: розминка + урок", LEARN))
        self.assertEqual(overload(self.day(keep), d(19), work_project="Work"), {})

    def test_too_many_real_tasks(self):
        flags = overload(self.day([(f"Задача {n}", JOB) for n in range(9)] + [("Перевірка, 2 хв", JOB)] * 5),
                         d(19), work_project="Work")
        self.assertIn("9 задач", flags[d(20)])          # the five 2-minute checks don't count

    def test_hours_alone_trigger(self):
        flags = overload(self.day([("Стенд, ~5 год", JOB), ("Набір, ~3,5 год", JOB)]), d(19), work_project="Work")
        self.assertIn("~8,5 год", flags[d(20)])

    def test_scope_ranges_and_personal_tasks_do_not_count(self):
        items = self.day([("Крок 6 бота (борди, вітрина ~15-20 год): робимо / ні", JOB)]) + \
                [Item(str(n), f"Gym {n}, ~3 год", "Habits", due=d(20)) for n in range(9)]
        self.assertEqual(overload(items, d(19), work_project="Work"), {})

    def test_brief_and_widget_show_the_warning_first(self):
        first = render(self.day(TUE), d(19), NOW, work_project="Work").split("\n")[0]
        self.assertTrue(first.startswith("⚠️ ПЕРЕВАНТАЖЕНО: вт 20.10: "), first)
        self.assertIn("SQL ×3", first)


if __name__ == "__main__":
    unittest.main()
