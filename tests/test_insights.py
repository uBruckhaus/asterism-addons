"""Insights tests. They need an Asterism checkout for the loader and the session type:
ASTERISM=/path/to/asterism (default ~/Projects/asterism)."""

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
ASTERISM = Path(os.environ.get("ASTERISM") or Path.home() / "Projects/asterism")
sys.path.insert(0, str(ASTERISM))
import addon_api  # noqa: E402
import addons  # noqa: E402
import claude_sessions as cs  # noqa: E402

sys.dont_write_bytecode = True        # no __pycache__ inside the add-on folder: it would be signed into it
spec = importlib.util.spec_from_file_location("insights", ROOT / "insights/addon.py")
ins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ins)


def atomic_write(path, text):
    import ai_core
    ai_core.atomic_write(path, text)


class ClaudeTitlesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "projects"
        (self.root / "p").mkdir(parents=True)
        self.file = self.root / "p" / "s.jsonl"
        self.cache = Path(self.tmp.name) / "titles.json"

    def write(self, *entries):
        self.file.write_text("".join(json.dumps(e) + "\n" for e in entries))

    def test_titles_only_from_title_lines_and_plain(self):
        self.write({"type": "user", "sessionId": "s1", "message": {"content": '{"type":"ai-title","aiTitle":"fake"}'}},
                   {"type": "ai-title", "sessionId": "s1", "aiTitle": "Fix the <b>map</b>\n\x1b[31m"},
                   {"type": "ai-title", "sessionId": "../x", "aiTitle": "bad id"})
        titles = ins.claude_titles(self.root, self.cache, atomic_write)
        self.assertEqual(list(titles), ["s1"])            # not the fake one inside a user message, not "../x"
        self.assertTrue(titles["s1"].startswith("Fix the <b>map</b>"))   # shown as plain text, never markup
        self.assertFalse(any(not c.isprintable() for c in titles["s1"]))
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o600)

    def test_links_are_not_followed(self):
        target = Path(self.tmp.name) / "elsewhere.jsonl"
        target.write_text(json.dumps({"type": "ai-title", "sessionId": "s9", "aiTitle": "secret"}) + "\n")
        (self.root / "p" / "link.jsonl").symlink_to(target)
        self.assertEqual(ins.claude_titles(self.root, self.cache, atomic_write), {})

    def test_long_titles_are_cut(self):
        self.assertEqual(len(ins.clean_title("x" * 1000)), ins.MAX_TITLE)


class DatabaseTitlesTest(unittest.TestCase):
    def test_top_level_titles_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opencode.db"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE session_v2 (id TEXT, parent_id TEXT, title TEXT, time_created INTEGER)")
            db.executemany("INSERT INTO session_v2 VALUES (?, ?, ?, ?)",
                           [("a", None, "Fix the parser", 2), ("b", "a", "child", 3), ("c", None, "bad\x1b[31m", 1)])
            db.commit()
            db.close()
            self.assertEqual(ins.db_titles(sqlite3.connect(path), ins.OPENCODE_SQL),
                             {"a": "Fix the parser", "c": "bad [31m"})
        self.assertEqual(ins.db_titles(None, ins.OPENCODE_SQL), {})


class TopicsTest(unittest.TestCase):
    def test_same_title_is_one_topic_ranked_by_tokens(self):
        now = time.time()
        sessions = {
            "a": cs.Session(cwd="/p", last=now, active=60, tokens={"m": [100, 50, 9999, 10]}),   # 160: cache reads apart
            "b": cs.Session(cwd="/q", last=now - 5, active=30, tokens={"m": [40, 0, 0, 0]}),
            "c": cs.Session(cwd="/p", last=now, active=10, tokens={"m": [500, 0, 0, 0]}),
            "d": cs.Session(cwd="/p", last=now, active=10, tokens={"m": [7, 0, 0, 0]}),
            "e": cs.Session(cwd="/p", last=now, active=10, tokens={"m": [70, 0, 0, 0]}),
            "old": cs.Session(cwd="/p", last=now - 40 * 86400, tokens={"m": [10 ** 6, 0, 0, 0]}),
        }
        titles = {"a": "Fix the map", "b": "fix  the MAP", "c": "Manual", "old": "Manual"}
        ranked, total = ins.topics(sessions, titles, now - 30 * 86400)
        self.assertEqual(total, 160 + 40 + 500 + 7 + 70)                  # the old session is out
        self.assertEqual([(t["title"], t["tokens"]) for t in ranked],
                         [("Manual", 500), ("Fix the map", 200), (None, 77)])
        fix = ranked[1]
        self.assertEqual((fix["sessions"], fix["active"], fix["folders"]), (2, 90, {"/p", "/q"}))

    def test_no_sessions_no_topics(self):
        self.assertEqual(ins.topics({}, {}, 0), ([], 0))


class SummaryTest(unittest.TestCase):
    def test_titles_and_numbers_only(self):
        now = time.time()
        sessions = {"s1": cs.Session(cwd="/home/u/p", last=now, active=600, replies=3, tokens={"m": [1, 2, 3, 4]})}
        text = ins.summary_text(sessions, {"s1": "Fix the map"}, now - 86400, "Hermes")
        self.assertIn("my Hermes sessions", text)
        self.assertIn("Fix the map", text)
        self.assertIn("10 min", text)
        self.assertLessEqual(len(ins.summary_text({f"s{i}": sessions["s1"] for i in range(5000)}, {}, 0, "x")),
                             ins.MAX_SUMMARY_INPUT)

    def test_run_summary_is_locked_down(self):
        api = mock.Mock()
        api.run_bounded.return_value = (b"Mostly \x1b[1mmaps\x00.", True)
        with mock.patch.object(ins.shutil, "which", return_value="/usr/bin/claude"):
            ok, answer = ins.run_summary(api, "titles")
        argv = api.run_bounded.call_args[0][0]
        for flag in ("-p", "--permission-mode", "plan", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flag, argv)
        self.assertEqual(api.run_bounded.call_args[1]["stdin"], b"titles")
        self.assertTrue(ok)
        self.assertNotIn("\x1b", answer)
        self.assertNotIn("\x00", answer)


@unittest.skipUnless(shutil.which("ssh-keygen"), "needs OpenSSH's ssh-keygen")
class LoadsInAsterismTest(unittest.TestCase):
    """Built and signed as tools/release.sh does it (with a throw-away key), then verified and loaded
    by Asterism's own loader."""

    def test_release_verifies_and_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = tmp / "key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", str(key)], check=True)
            copy = tmp / "repo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("dist", "__pycache__", ".git", "catalog.json",
                                                                  "catalog.sig"))
            subprocess.run([str(copy / "tools/release.sh"), "insights"], check=True, capture_output=True,
                           env={**os.environ, "KEY": str(key)})
            signers = f'{addons.PRINCIPAL} namespaces="{addons.NAMESPACE}" ' + \
                " ".join(key.with_suffix(".pub").read_text().split()[:2])
            self.assertTrue(addons.signature_ok((copy / "catalog.json").read_bytes(), (copy / "catalog.sig").read_bytes(),
                                                signers))
            import zipfile
            version = json.loads((ROOT / "insights/addon.json").read_text())["version"]
            zipfile.ZipFile(copy / f"dist/insights-{version}.zip").extractall(tmp / "installed")
            addon = addons.verify(tmp / "installed/insights", signers)
            self.assertEqual((addon.state, addon.name), ("verified", "Insights"))
            hooks = addon_api.Hooks()
            with mock.patch("pathlib.Path.home", return_value=tmp):
                addons.load(addon, hooks)
            self.assertEqual(addon.state, "loaded", addon.reason)
            self.assertEqual(set(hooks.titles), {"claude", "opencode", "hermes"})
            self.assertEqual(len(hooks.details), 1)
            self.assertEqual(hooks.privacy, {"insights": 3})


if __name__ == "__main__":
    unittest.main()
