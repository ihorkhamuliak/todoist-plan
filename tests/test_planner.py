import sys, unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import timezone, timedelta
from planner import Item, plan, render, split_due

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

    def test_personal_today_and_overdue_fold_into_one_basic_line(self):
        items = [Item("w", "Client session", "Work", due=SUN),
                 Item("h", "Morning exercise, yoga and a cold shower", "Habits", due=SUN, recurring=True),
                 Item("b", "Pay internet", "Home", due=d(2)),
                 Item("f", "Birthday", "Home", due=d(6))]
        text = render(items, SUN, NOW, work_project="Work")
        lines = text.split("\n")
        self.assertEqual(lines[0], "БАЗОВЕ: Pay internet (−2 дн) · Morning exercise, yoga and a c…")
        self.assertNotIn("ПРОСТРОЧЕНЕ", text)       # personal overdue lives in the basic line
        self.assertIn("СЬОГОДНІ\n· Client session", text)
        self.assertIn("ВТ 06.10\nБАЗОВЕ: Birthday", text)  # future days fold personal tasks too

    def test_day_with_only_personal_tasks_still_shows(self):
        text = render([Item("h", "Gym", "Habits", due=d(5))], SUN, NOW, work_project="Work")
        self.assertIn("ПН 05.10\nБАЗОВЕ: Gym", text)

    def test_footer_counts_closed_today(self):
        self.assertTrue(render([], SUN, NOW, closed_today=4).endswith("закрито сьогодні: 4 · без дати: 0 · оновлено 21:40"))

    def test_warning_goes_first(self):
        text = render([], SUN, NOW, warning="⚠️ Todoist offline")
        self.assertTrue(text.startswith("⚠️ Todoist offline\n"))
        self.assertTrue(text.endswith("без дати: 0 · оновлено 21:40"))


if __name__ == "__main__":
    unittest.main()
