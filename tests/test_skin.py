"""The Rainmeter skin colors lines by regex. These tests run the skin's own patterns against real render output,
so renaming a label in planner.py without the skin (or the other way round) fails here, not silently on the desktop."""
import re, sys, unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planner import Item, render

INI = ROOT / "rainmeter" / "PlanDay" / "PlanDay.ini"
SUN = date(2026, 10, 4)


def patterns():
    text = INI.read_bytes().decode("ascii")  # Rainmeter misreads UTF-8 skins: any non-ASCII byte fails here
    raw = dict(re.findall(r"^(InlinePattern\d*)=(.*)$", text, re.M))
    return {k: re.sub(r"\\x\{([0-9A-F]{4})\}", lambda m: chr(int(m.group(1), 16)), v) for k, v in raw.items()}


def sample(lang):
    items = [Item("o", "Report", "Work", due=date(2026, 10, 2), priority=4),
             Item("t", "Client session", "Work", due=SUN, priority=3),
             Item("h", "Gym", "Habits", due=date(2026, 10, 3)),
             Item("n", "Plan", "Work", due=date(2026, 10, 5), priority=2)]
    text = render(items, SUN, datetime(2026, 10, 4, 8, 0), work_project="Work", closed_today=1, lang=lang)
    # the way Rainmeter gets it: written with todo.py's encoding, read as UTF-16LE (CodePage=1200), BOM kept
    enc = re.search(r'widget_file"\]\)\.write_text\(text, encoding="([^"]+)"\)', (ROOT / "todo.py").read_text("utf-8"))[1]
    return text.encode(enc).decode("utf-16-le").split("\n")


class Skin(unittest.TestCase):
    def test_skin_is_ascii(self):
        patterns()

    def test_patterns_hit_the_right_lines(self):
        p = patterns()
        for lang in ("uk", "en"):
            lines = sample(lang)
            hit = lambda key: [l for l in lines if re.search(p[key], l)]
            with self.subTest(lang=lang):
                self.assertEqual(len(hit("InlinePattern")), 3)            # overdue, today, next day headers
                self.assertEqual(len(hit("InlinePattern3")), 1)           # overdue header in red, first line
                self.assertEqual(hit("InlinePattern4"), [lines[3]])       # personal line green, under today
                self.assertTrue(lines[3].startswith(("БАЗОВЕ: Gym", "ESSENTIALS: Gym")))
                self.assertEqual(len(hit("InlinePattern10")), 2)          # "−2 d" tails red, in the green line too
                self.assertEqual(hit("InlinePattern8"), [lines[-1]])      # footer grey


if __name__ == "__main__":
    unittest.main()
