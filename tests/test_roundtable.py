import json
import os
import subprocess
import sys
import signal
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/llm-roundtable/scripts/roundtable.py"
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

    def test_prefers_ballot_with_valid_vote(self):
        text = 'example {"vote": "<option id>"} ... broken {"vote": "B", "risks": [] junk} final {"vote": "A", "evidence": []}'
        self.assertEqual(rt.parse_ballot(text, ["A", "B"])["vote"], "A")
        self.assertEqual(rt.parse_ballot('{"vote": "Z"}', ["A", "B"])["vote"], "Z")

    def test_nested_vote_in_rebuttal_is_ignored(self):
        text = '{"vote": "B", "evidence": [], "rebuttals": [{"member": "M1", "quote": {"vote": "A"}}]}'
        self.assertEqual(rt.parse_ballot(text, ["A", "B"])["vote"], "B")

    def test_malformed_fields_do_not_raise(self):
        b = rt.normalize_ballot({"vote": "A", "ratings": ["M1", 2], "evidence": 5, "confidence": float("inf"),
                                 "risks": "one risk"}, ["A", "B"])
        self.assertEqual((b["ratings"], b["evidence"], b["confidence"], b["risks"]), ({}, [], 0.5, ["one risk"]))
        b = rt.normalize_ballot({"vote": "A", "ratings": {"M1": "inf", "M2": 1}}, ["A", "B"])
        self.assertEqual(b["ratings"], {"M2": 1})

    def test_fact_without_source_is_an_assumption(self):
        r = rt.classify({"rc": 0, "text": '{"vote": "A", "evidence": [{"type": "FACT", "claim": "x", "source": ""}]}', "noise": ""}, ["A", "B"])
        self.assertEqual(r["status"], "no_evidence")

    def test_unsourced_inference_is_an_assumption(self):
        r = rt.classify({"rc": 0, "text": '{"vote": "A", "evidence": [{"type": "INFERENCE", "claim": "x"}]}', "noise": ""}, ["A", "B"])
        self.assertEqual(r["status"], "no_evidence")

    def test_fill_is_single_pass(self):
        out = rt.fill("-p={prompt}", {"model": "m", "prompt": "see {out_file}", "prompt_file": "/pf", "out_file": "/of"})
        self.assertEqual(out, "-p=see {out_file}")

    def test_ballot_in_noise_is_ignored(self):
        r = rt.classify({"rc": 0, "text": "", "noise": '{"vote": "A", "evidence": [{"type": "FACT", "claim": "x", "source": "y"}]}'}, ["A", "B"])
        self.assertEqual(r["status"], "invalid")

    def test_seat_env_drops_unrelated_credentials(self):
        os.environ.update(GH_TOKEN="x", ANTHROPIC_API_KEY="y", AWS_SECRET_ACCESS_KEY="z", PATH_EXTRA="p")
        env = rt.seat_env("s", auth=("ANTHROPIC_",))
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertEqual((env["ANTHROPIC_API_KEY"], env["PATH_EXTRA"], env["ROUNDTABLE_SEAT"]), ("y", "p", "s"))

    def test_seat_env_pwd_follows_seat_cwd(self):
        # opencode resolves its project from $PWD; an inherited PWD let it work in the caller's checkout
        os.environ.update(PWD="/caller/checkout", OLDPWD="/elsewhere")
        env = rt.seat_env("s", "/tmp/seat-sandbox")
        self.assertEqual(env["PWD"], "/tmp/seat-sandbox")
        self.assertNotIn("OLDPWD", env)

    def test_classify_quota_and_unavailable(self):
        q = rt.classify({"rc": 1, "text": "", "noise": "Error: rate limit exceeded"}, ["A", "B"])
        u = rt.classify({"rc": 1, "text": "", "noise": "Couldn't set model: unknown model id"}, ["A", "B"])
        self.assertEqual((q["status"], u["status"]), ("quota", "unavailable"))
        s = rt.classify({"rc": 1, "text": "", "noise": "You've hit your session limit · resets 11pm (Asia/Saigon)"}, ["A", "B"])
        self.assertEqual(s["status"], "quota")

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

    def test_count_mode_uses_score_before_fable(self):
        st = {"fable": seat_state("B", tiebreak=True, received=[0]), "x": seat_state("A", received=[2])}
        t = rt.tally(st, OPTS, "count")
        self.assertEqual((t["verdict"], t["tiebreak"]), ("A", None))

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


def make_repo():
    ws = Path(tempfile.mkdtemp())
    if subprocess.run(["git", "init", "-q", str(ws)], capture_output=True).returncode != 0:
        raise unittest.SkipTest("git init not possible here")
    return ws


class EndToEndTest(unittest.TestCase):
    def run_council(self, seats, presets, extra=(), expect_rc=(0, 3)):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"adapters": {"fake": {"bin": sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True},
                            "fake-isolated": {"bin": sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True, "isolate": True}},
               "seats": seats, "presets": presets}
        (tmp / "cfg.json").write_text(json.dumps(cfg))
        (tmp / "brief.md").write_text("# Pick one\n\nWhich?\n\n## Options\n- A: first\n- B: second\n")
        env = dict(os.environ, ROUNDTABLE_RUNS=str(tmp / "runs"))
        env.pop("ROUNDTABLE_SEAT", None)
        p = subprocess.run([sys.executable, str(SCRIPT), "--config", str(tmp / "cfg.json"), "run", "--brief", str(tmp / "brief.md"),
                            "--seats", "t", "--out", str(tmp / "run"), "--seed", "1", "--timeout", "60", *extra],
                           capture_output=True, text=True, env=env)
        self.assertIn(p.returncode, expect_rc, p.stderr)
        res = json.loads((tmp / "run/result.json").read_text())
        res["_run_dir"] = str(tmp / "run")
        self.assertTrue(p.stdout.rstrip().splitlines()[-1].startswith("VERDICT: "))
        self.assertTrue((tmp / "run/r1").is_dir(), "transcripts are published after the round")
        return res, (tmp / "run/decision.md").read_text()

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
        # s2 was rated on its round-1 B and then switched to A: its rating must not weigh the new vote
        self.assertEqual(res["seats"]["s2"]["ratings_received"], [])

    def test_default_applies_when_council_cannot_decide(self):
        seats = [{"id": "x", "adapter": "fake", "models": ["vote-A"]}, {"id": "y", "adapter": "fake", "models": ["vote-B"]}]
        res, md = self.run_council(seats, {"t": ["x", "y"]}, ["--rounds", "1", "--default", "b"])
        self.assertEqual((res["tally"]["verdict"], res["tally"]["decided_by"]), ("B", "default"))
        self.assertIn("safe default", md)

    def test_invalid_ballots_do_not_rate_others(self):
        seats = [{"id": "s1", "adapter": "fake", "models": ["vote-A"]},
                 {"id": "s2", "adapter": "fake", "models": ["vote-B"]},
                 {"id": "s3", "adapter": "fake", "models": ["vote-A-bare"]}]
        res, _ = self.run_council(seats, {"t": ["s1", "s2", "s3"]})
        self.assertEqual(res["seats"]["s3"]["status"], "no_evidence")
        self.assertEqual(res["seats"]["s2"]["ratings_received"], [0])  # only s1's rating, not s3's

    def test_no_quorum(self):
        seats = [{"id": "a", "adapter": "fake", "models": ["quota"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, md = self.run_council(seats, {"t": ["a", "b"]})
        self.assertTrue(res["tally"].get("no_quorum"))
        self.assertEqual(res["tally"]["decided_by"], "none")
        self.assertIn("NO QUORUM", md)

    def test_workspace_write_is_flagged(self):
        ws = make_repo()
        seats = [{"id": "a", "adapter": "fake", "models": ["write-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, md = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1", "--workspace", str(ws / ".")], expect_rc=(3,))
        self.assertTrue(res["workspace_changed"])
        self.assertIn("WARNING", md)
        # fail closed: nothing actionable
        self.assertEqual((res["tally"]["verdict"], res["tally"]["decided_by"]), (None, "workspace_changed"))
        run = Path(res["_run_dir"])
        st = subprocess.run([sys.executable, str(SCRIPT), "status", str(run)], capture_output=True, text=True)
        self.assertEqual(st.returncode, 4)
        self.assertIn("TAINTED", st.stdout)
        self.assertEqual(st.stdout.rstrip().splitlines()[-1], "VERDICT: NONE (workspace_changed)")

    def test_status_prints_verdict(self):
        seats = [{"id": "x", "adapter": "fake", "models": ["vote-A"]}, {"id": "y", "adapter": "fake", "models": ["vote-A"]}]
        res, _ = self.run_council(seats, {"t": ["x", "y"]}, ["--rounds", "1"])
        st = subprocess.run([sys.executable, str(SCRIPT), "status", res["_run_dir"]], capture_output=True, text=True)
        self.assertEqual(st.returncode, 0)
        self.assertEqual(st.stdout.rstrip().splitlines()[-2:], ["DONE", "VERDICT: A (council)"])

    @unittest.skipUnless(hasattr(os, "fork"), "needs fork")
    def test_detach_returns_at_once_and_finishes(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"adapters": {"fake": {"bin": sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True}},
               "seats": [{"id": "x", "adapter": "fake", "models": ["vote-A"]}, {"id": "y", "adapter": "fake", "models": ["vote-A"]}],
               "presets": {"t": ["x", "y"]}}
        (tmp / "cfg.json").write_text(json.dumps(cfg))
        (tmp / "brief.md").write_text("# Pick one\n\n## Options\n- A: first\n- B: second\n")
        env = dict(os.environ, ROUNDTABLE_RUNS=str(tmp / "runs"))
        env.pop("ROUNDTABLE_SEAT", None)
        # the caller's process group is killed right after it returns, as Codex does with tool calls
        p = subprocess.Popen([sys.executable, str(SCRIPT), "--config", str(tmp / "cfg.json"), "run", "--brief", str(tmp / "brief.md"),
                              "--seats", "t", "--rounds", "1", "--timeout", "60", "--detach"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, err)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        run = Path(out.strip().splitlines()[0])
        self.assertTrue(run.is_dir())
        deadline = time.time() + 60
        while time.time() < deadline and not (run / "decision.md").exists():
            time.sleep(0.5)
        st = subprocess.run([sys.executable, str(SCRIPT), "status", str(run)], capture_output=True, text=True)
        self.assertIn("VERDICT: A (council)", st.stdout)
        self.assertTrue((run / "runner.log").exists())

    def test_subdirectory_workspace_is_watched(self):
        ws = make_repo()
        (ws / "sub").mkdir()
        seats = [{"id": "a", "adapter": "fake", "models": ["write-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, _ = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1", "--workspace", str(ws / "sub")], expect_rc=(3,))
        self.assertTrue(res["workspace_changed"])

    def test_isolated_seat_writes_only_its_snapshot(self):
        ws = make_repo()
        (ws / "file.txt").write_text("x")
        seats = [{"id": "a", "adapter": "fake-isolated", "models": ["write-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, md = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1", "--workspace", str(ws)], expect_rc=(0,))
        self.assertFalse(res["workspace_changed"])
        self.assertFalse((ws / "written-by-seat.txt").exists())

    def test_tie_without_tiebreak_has_no_dissent_section(self):
        seats = [{"id": "x", "adapter": "fake", "models": ["vote-A"]}, {"id": "y", "adapter": "fake", "models": ["vote-B"]}]
        res, md = self.run_council(seats, {"t": ["x", "y"]}, ["--rounds", "1"])
        self.assertIsNone(res["tally"]["verdict"])
        self.assertIn("TIE", md)
        self.assertNotIn("## Dissent", md)

    def test_missing_ballot_gets_one_nudge(self):
        seats = [{"id": "a", "adapter": "fake", "models": ["lazy-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}]
        res, _ = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1"])
        self.assertEqual(res["seats"]["a"]["status"], "ok")

    def test_status_reports_dead_runner(self):
        tmp = Path(tempfile.mkdtemp())
        run = tmp / "runs" / "20260101-000000-x"
        run.mkdir(parents=True)
        (run / "meta.json").write_text(json.dumps({"pid": 999999}))
        (tmp / "runs" / "doctor-20990101-000000").mkdir()  # newer, but not a run
        p = subprocess.run([sys.executable, str(SCRIPT), "status"], capture_output=True, text=True,
                           env=dict(os.environ, ROUNDTABLE_RUNS=str(tmp / "runs")))
        self.assertIn("FAILED", p.stdout)
        self.assertIn("20260101-000000-x", p.stdout)

    def test_quota_word_in_echoed_files_is_not_quota(self):
        noise = "cat tests.py\n'models': ['quota']\n" + "\n".join("x%d" % i for i in range(30)) + "\nError: connection reset"
        self.assertEqual(rt.classify({"rc": 1, "text": "", "noise": noise}, ["A", "B"])["status"], "error")

    def test_timeout_walks_to_fallback(self):
        # b uses a different model id: a fallback equal to another seat's primary would be dropped
        seats = [{"id": "a", "adapter": "fake", "models": ["slow", "vote-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A-2"]}]
        res, _ = self.run_council(seats, {"t": ["a", "b"]}, ["--rounds", "1", "--timeout", "2"])
        self.assertEqual([a["status"] for a in res["seats"]["a"]["history"][0]["attempts"]], ["timeout", "ok"])

    def test_sigterm_kills_seats_without_fallback(self):
        import signal as sg
        import time as tm
        tmp = Path(tempfile.mkdtemp())
        cfg = {"adapters": {"fake": {"bin": sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True}},
               "seats": [{"id": "a", "adapter": "fake", "models": ["slow", "vote-A"]},
                         {"id": "b", "adapter": "fake", "models": ["slow"]}], "presets": {"t": ["a", "b"]}}
        (tmp / "cfg.json").write_text(json.dumps(cfg))
        (tmp / "brief.md").write_text("# x\n\n## Options\n- A: a\n- B: b\n")
        env = dict(os.environ, ROUNDTABLE_RUNS=str(tmp / "runs"))
        env.pop("ROUNDTABLE_SEAT", None)
        p = subprocess.Popen([sys.executable, str(SCRIPT), "--config", str(tmp / "cfg.json"), "run", "--brief", str(tmp / "brief.md"),
                              "--seats", "t", "--out", str(tmp / "run")], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tm.sleep(2)
        t0 = tm.time()
        p.send_signal(sg.SIGTERM)
        p.wait(timeout=20)
        self.assertLess(tm.time() - t0, 10)
        self.assertEqual(p.returncode, 128 + sg.SIGTERM)
        self.assertNotIn("vote-A", (tmp / "run/progress.log").read_text(), "fallback model must not start after a stop")
        out = subprocess.run(["pgrep", "-f", str(FAKE) + " slow"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "", "seat processes must be gone")

    def test_recursion_guard(self):
        p = subprocess.run([sys.executable, str(SCRIPT), "run", "--brief", "-"], input="x", capture_output=True, text=True,
                           env=dict(os.environ, ROUNDTABLE_SEAT="opus"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("inside a council seat", p.stderr)


if __name__ == "__main__":
    unittest.main()
