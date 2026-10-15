"""OpenCode model ranking (prefer), the bundled models.dev snapshot and tools/update_models.py."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_roundtable import rt

ROOT = Path(__file__).resolve().parent.parent
META = {
    "muse-spark-1.3-contributor-free": {"family": "muse-free", "name": "Muse Spark 1.3 Free", "release_date": "2026-09-02", "cost": {"input": 0}},
    "muse-spark-1.2-contributor-free": {"family": "muse-free", "release_date": "2026-08-05", "status": "deprecated", "cost": {"input": 0}},
    "cat-jam-free": {"release_date": "2026-10-12", "cost": {"input": 0}},
    "space-bunny-free": {"release_date": "2026-09-23", "cost": {"input": 0}},
    "gemini-x-free": {"family": "gemini", "release_date": "2026-10-13", "cost": {"input": 0}},
    "big-pickle": {"family": "big-pickle", "release_date": "2025-10-17", "cost": {"input": 0}},
    "muse-spark-1.3": {"family": "muse", "release_date": "2026-09-02", "cost": {"input": 1.25}},
}
LISTED = ["opencode/" + m for m in META]


class RankFreeModelsTest(unittest.TestCase):
    def test_newest_first_without_prefer(self):
        got = rt.rank_free_models(LISTED, META, exclude="gemini")
        self.assertEqual(got, ["opencode/cat-jam-free", "opencode/space-bunny-free",
                               "opencode/muse-spark-1.3-contributor-free", "opencode/big-pickle"])

    def test_prefer_goes_first_and_skips_deprecated_and_paid(self):
        got = rt.rank_free_models(LISTED, META, exclude="gemini", prefer=["muse-spark"])
        self.assertEqual(got[:2], ["opencode/muse-spark-1.3-contributor-free", "opencode/cat-jam-free"])
        self.assertNotIn("opencode/muse-spark-1.2-contributor-free", got)  # deprecated
        self.assertNotIn("opencode/muse-spark-1.3", got)  # not free

    def test_prefer_order_and_name_match(self):
        got = rt.rank_free_models(LISTED, META, prefer=["pickle", "Muse Spark"])
        self.assertEqual(got[:2], ["opencode/big-pickle", "opencode/muse-spark-1.3-contributor-free"])

    def test_dead_and_excluded_never_picked(self):
        got = rt.rank_free_models(LISTED, META, exclude="gemini", prefer=["muse"],
                                  dead={"opencode/muse-spark-1.3-contributor-free"})
        self.assertEqual(got[0], "opencode/cat-jam-free")
        self.assertNotIn("opencode/gemini-x-free", got)

    def test_seat_config_passes_prefer(self):
        cfg = rt.load_config(str(ROOT / "skills/llm-roundtable/scripts/seats.json"))
        seat = next(s for s in cfg["seats"] if s["id"] == "opencode")
        self.assertEqual(seat["prefer"], ["muse-spark"])
        for prefer in (["muse-spark"], "muse-spark"):  # a single string is accepted too
            cfg["seats"] = [dict(seat, prefer=prefer)]
            with mock.patch.object(rt, "opencode_free_models", return_value=["opencode/a", "opencode/b"]) as f:
                seats, _ = rt.resolve_seats(cfg, ["opencode"])
            self.assertEqual(f.call_args[0][1], ["muse-spark"])
            self.assertEqual(seats[0]["models"], ["opencode/a", "opencode/b"])


class SnapshotTest(unittest.TestCase):
    def test_bundled_snapshot_is_used_when_models_dev_is_down(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(rt, "RUNS_DIR", Path(d) / "runs"), \
                 mock.patch.object(rt.urllib.request, "urlopen", side_effect=OSError("offline")):
                meta = rt.models_dev_opencode()
        self.assertTrue(meta)
        self.assertEqual(meta, rt.opencode_snapshot())
        self.assertTrue(all("free" in m or (v.get("cost") or {}).get("input") == 0 for m, v in meta.items()))


class UpdateModelsToolTest(unittest.TestCase):
    def api(self):
        return {"openai": {"models": {"gpt-6.1-sol": {"family": "gpt-sol", "release_date": "2026-09-29"}}},
                "xai": {"models": {"grok-4.7": {"family": "grok", "release_date": "2026-09-21"}}},
            "opencode": {"models": dict(META, **{"paid-x": {"release_date": "2026-10-01", "cost": {"input": 3}}})},
            "anthropic": {"models": {
                "claude-fable-5-1": {"family": "claude-fable", "release_date": "2026-09-01"},
                "claude-fable-5-2": {"family": "claude-fable", "release_date": "2026-10-10", "modalities": {"output": ["text"]}},
                "claude-opus-5-5": {"family": "claude-opus", "release_date": "2026-09-22"}}},
            "google": {"models": {
                "gemini-3.8-flash": {"family": "gemini-flash", "release_date": "2026-09-02"},
                "gemini-3.9-flash-image": {"family": "gemini-flash", "release_date": "2026-10-01"}}},
        }

    def run_tool(self, api, *extra):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "api.json"
            p.write_text(json.dumps(api))
            return subprocess.run([sys.executable, str(ROOT / "tools/update_models.py"), "--api", str(p), "--check"] + list(extra),
                                  capture_output=True, text=True)

    def test_watch_report_and_snapshot(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import update_models as um
        api = self.api()
        snap = um.snapshot(api)
        self.assertIn("muse-spark-1.3-contributor-free", snap["models"])
        self.assertNotIn("paid-x", snap["models"])
        cfg = json.loads((ROOT / "skills/llm-roundtable/scripts/seats.json").read_text())
        report = um.watch(api, cfg, snap)
        self.assertIn("| fable | `claude-fable-5-1` | 2026-09-01 | `claude-fable-5-2` |", report)
        self.assertIn("| gemini | `gemini-3.8-flash-high` | 2026-09-02 | none |", report)  # image model ignored
        self.assertIn("| opencode | `opencode/muse-spark-1.3-contributor-free` |", report)
        self.assertNotIn("codex-6", report)  # homogeneous helper seats are not watched

    def test_refuses_partial_answers(self):
        for api in ({"anthropic": {"models": {}}},  # no opencode
                    dict(self.api(), xai={"models": {}}),  # a fixed-seat provider missing
                    dict(self.api(), opencode={"models": {"paid": {"cost": {"input": 1}}}})):  # no free model left
            r = self.run_tool(api)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("refusing", r.stderr)

    def test_no_release_date_means_nothing_newer(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import update_models as um
        api = {"anthropic": {"models": {"a-1": {"family": "a"}, "a-2": {"family": "a", "release_date": "2026-10-01"}}}}
        self.assertEqual(um.newer_in_family(api, "claude", "a-1")[1], [])

    def test_free_needs_zero_input_and_output(self):
        self.assertTrue(rt.is_free("x-free", {"cost": {"input": 1}}))
        self.assertTrue(rt.is_free("x", {"cost": {"input": 0, "output": 0}}))
        self.assertFalse(rt.is_free("x", {"cost": {"input": 0, "output": 2}}))


if __name__ == "__main__":
    unittest.main()
