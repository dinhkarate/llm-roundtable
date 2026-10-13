import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/roundtable/scripts/roundtable.py"
FAKE = Path(__file__).resolve().parent / "fake_cli.py"
sys.path.insert(0, str(SCRIPT.parent))
import roundtable as rt  # noqa: E402

OPTS = [("A", "first"), ("B", "second")]


def seat_state(vote, status="ok", tiebreak=False, received=None, weight=1.0):
    b = {"vote": vote, "confidence": 0.5, "summary": "", "evidence": [{"type": "FACT", "claim": "x", "source": "y"}]}
    return {"status": status, "ballot": b, "tiebreak": tiebreak, "ratings_received": received or [], "weight": weight}


class ParseTest(unittest.TestCase):
    def test_fenced_last_ballot_wins(self):
        text = 'draft {"vote": "A"}\n```json\n{"vote": "b", "evidence": []}\n```'
        self.assertEqual(rt.parse_ballot(text)["vote"], "b")

    def test_normalize_vote_and_ratings(self):
        b = rt.normalize_ballot({"vote": "(b) second", "confidence": 3, "ratings": {"m1": "1.6"}}, ["A", "B"])
        self.assertEqual(b["vote"], "B")
        self.assertEqual(b["confidence"], 1.0)
        self.assertEqual(b["ratings"], {"M1": 2})

    def test_classify_quota_and_unavailable(self):
        q = rt.classify({"rc": 1, "text": "", "noise": "Error: rate limit exceeded"}, ["A", "B"])
        u = rt.classify({"rc": 1, "text": "", "noise": "Couldn't set model: unknown model id"}, ["A", "B"])
        self.assertEqual((q["status"], u["status"]), ("quota", "unavailable"))

    def test_no_evidence_is_flagged(self):
        r = rt.classify({"rc": 0, "text": '{"vote": "A", "evidence": [{"type": "ASSUMPTION", "claim": "x"}]}', "noise": ""}, ["A", "B"])
        self.assertEqual(r["status"], "no_evidence")

    def test_secret_scan(self):
        self.assertTrue(rt.secret_scan("token: ghp_" + "a" * 36))
        self.assertFalse(rt.secret_scan("choose between postgres and sqlite"))


class TallyTest(unittest.TestCase):
    def test_weighted_majority(self):
        t = rt.tally({"a": seat_state("A"), "b": seat_state("A"), "c": seat_state("B")}, OPTS)
        self.assertEqual(t["verdict"], "A")

    def test_peer_ratings_change_weight(self):
        # 2 votes with weak evidence (0.5 each) lose to 1 vote with strong evidence (1.5)
        st = {"a": seat_state("A", received=[0, 0]), "b": seat_state("A", received=[0]), "c": seat_state("B", received=[2, 2])}
        self.assertEqual(rt.tally(st, OPTS)["verdict"], "B")
        self.assertEqual(rt.tally(st, OPTS, "count")["verdict"], "A")

    def test_tie_goes_to_fable(self):
        t = rt.tally({"fable": seat_state("B", tiebreak=True), "opus": seat_state("A")}, OPTS)
        self.assertEqual(t["verdict"], "B")
        self.assertIn("fable", t["tiebreak"])

    def test_tie_without_fable_escalates(self):
        t = rt.tally({"x": seat_state("A"), "y": seat_state("B")}, OPTS)
        self.assertIsNone(t["verdict"])
        self.assertTrue(t["tie"])

    def test_invalid_ballots_do_not_count(self):
        t = rt.tally({"x": seat_state("A", status="no_evidence"), "y": seat_state("B")}, OPTS)
        self.assertEqual((t["verdict"], t["valid_votes"]), ("B", 1))


class EndToEndTest(unittest.TestCase):
    def run_council(self, seats, presets, extra=()):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"adapters": {"fake": {"bin": sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True}},
               "seats": seats, "presets": presets}
        (tmp / "cfg.json").write_text(json.dumps(cfg))
        (tmp / "brief.md").write_text("# Pick one\n\nWhich?\n\n## Options\n- A: first\n- B: second\n")
        env = dict(os.environ, ROUNDTABLE_RUNS=str(tmp / "runs"))
        env.pop("ROUNDTABLE_SEAT", None)
        p = subprocess.run([sys.executable, str(SCRIPT), "--config", str(tmp / "cfg.json"), "run", "--brief", str(tmp / "brief.md"),
                            "--seats", "t", "--out", str(tmp / "run"), "--seed", "1", "--timeout", "60", *extra],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads((tmp / "run/result.json").read_text()), (tmp / "run/decision.md").read_text()

    def test_fallback_unattended_and_fable_tiebreak(self):
        seats = [
            {"id": "fable", "adapter": "fake", "models": ["quota", "vote-B"], "tiebreak": True},
            {"id": "opus", "adapter": "fake", "models": ["vote-A"]},
            {"id": "gemini", "adapter": "fake", "models": ["quota", "unknown"]},
        ]
        res, md = self.run_council(seats, {"t": ["fable", "opus", "gemini"]}, ["--rounds", "1"])
        s = res["seats"]
        self.assertEqual((s["fable"]["model"], s["fable"]["level"]), ("vote-B", 1))
        self.assertEqual(s["gemini"]["status"], "unattended")
        self.assertEqual(res["tally"]["verdict"], "B")
        self.assertIn("UNATTENDED", md)
        self.assertIn("broken by fable", md)

    def test_cross_exam_flip_and_ratings(self):
        seats = [
            {"id": "s1", "adapter": "fake", "models": ["vote-A"]},
            {"id": "s2", "adapter": "fake", "models": ["flip-B-A"]},
            {"id": "s3", "adapter": "fake", "models": ["vote-B"]},
            {"id": "s4", "adapter": "fake", "models": ["prose"]},
        ]
        res, md = self.run_council(seats, {"t": ["s1", "s2", "s3", "s4"]})
        self.assertEqual(res["tally"]["verdict"], "A")
        self.assertEqual(res["tally"]["count"], {"A": 2, "B": 1})
        self.assertEqual(res["seats"]["s4"]["status"], "invalid")
        self.assertIn("Changed votes", md)
        # s3 voted B in round 1 and was rated 0 by the others (self-rating ignored)
        self.assertEqual(res["seats"]["s3"]["ratings_received"], [0, 0])

    def test_no_quorum(self):
        seats = [{"id": "a", "adapter": "fake", "models": ["quota"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, md = self.run_council(seats, {"t": ["a", "b"]})
        self.assertTrue(res["tally"].get("no_quorum"))
        self.assertIn("NO QUORUM", md)

    def test_workspace_write_is_flagged(self):
        ws = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(ws)], check=True)
        seats = [{"id": "a", "adapter": "fake", "models": ["write-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, md = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1", "--workspace", str(ws)])
        self.assertTrue(res["workspace_changed"])
        self.assertIn("WARNING", md)

    def test_recursion_guard(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "run", "--brief", "-"], input="x", capture_output=True, text=True,
                           env=dict(os.environ, ROUNDTABLE_SEAT="opus"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("inside a council seat", p.stderr)


if __name__ == "__main__":
    unittest.main()
