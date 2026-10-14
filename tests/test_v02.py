"""v0.2: usage, run --dry-run, result contract / status --json, kill criteria + UNKNOWN, framing check,
--min-margin and --deadline. Fake CLIs only (tests/fake_cli.py), no model calls."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from test_roundtable import FAKE, SCRIPT, make_repo, rt

OPTS = [("A", "first"), ("B", "second")]
OPTS3 = [("A", "first"), ("B", "second"), ("C", "third")]
BRIEF = "# Pick one\n\nWhich?\n\n## Options\n- A: first\n- B: second\n"


def ballot(vote, evidence=None, **extra):
    b = {"vote": vote, "confidence": 0.5, "summary": "s-%s" % vote,
         "evidence": evidence if evidence is not None else [{"type": "FACT", "claim": "x", "source": "y"}],
         "risks": [], "conditions": [], "kill_criteria": [], "restatement": "", "missing_option": ""}
    b.update(extra)
    return b


def seat(vote, status="ok", tiebreak=False, received=None, r1=None, **extra):
    """A seat state as cmd_run leaves it; r1 = the round-1 ballot kept in history (defaults to the final one)."""
    b = ballot(vote, **extra) if vote else None
    first = r1 if r1 is not None else b
    return {"status": status, "ballot": b, "tiebreak": tiebreak, "ratings_received": received or [], "weight": 1.0,
            "level": 0, "history": [{"status": status, "ballot": first, "attempts": []}]}


def meta(**kw):
    m = {"title": "t", "options": OPTS, "rounds": 1, "mode": "decide", "quorum": 2, "decision_rule": "weighted"}
    m.update(kw)
    return m


def state_of(votes, **kw):
    return {"s%d" % i: seat(v, **kw) for i, v in enumerate(votes)}


class KillCriteriaUnknownTest(unittest.TestCase):
    def test_unknown_only_ballot_is_no_evidence(self):
        text = '{"vote": "A", "evidence": [{"type": "UNKNOWN", "claim": "is it fast?", "source": "bench.md"}]}'
        self.assertEqual(rt.classify({"rc": 0, "text": text, "noise": ""}, ["A", "B"])["status"], "no_evidence")

    def test_unknown_plus_fact_counts_and_unknown_is_kept_apart(self):
        text = ('{"vote": "A", "evidence": [{"type": "UNKNOWN", "claim": "q"}, '
                '{"type": "FACT", "claim": "f", "source": "a.py:1"}]}')
        r = rt.classify({"rc": 0, "text": text, "noise": ""}, ["A", "B"])
        self.assertEqual(r["status"], "ok")
        self.assertEqual([e["type"] for e in r["ballot"]["evidence"]], ["UNKNOWN", "FACT"])
        self.assertEqual(rt.open_questions(r["ballot"])[0]["claim"], "q")

    def test_kill_criteria_optional_and_malformed(self):
        self.assertEqual(rt.normalize_ballot({"vote": "A"}, ["A"])["kill_criteria"], [])
        self.assertEqual(rt.normalize_ballot({"vote": "A", "kill_criteria": "If X, stop"}, ["A"])["kill_criteria"], ["If X, stop"])
        b = rt.normalize_ballot({"vote": "A", "kill_criteria": [{"if": "x"}, 5, "", None, "none"]}, ["A"])
        self.assertEqual(b["kill_criteria"], ["{'if': 'x'}", "5"])
        self.assertEqual(rt.normalize_ballot({"vote": "A", "kill_criteria": 7}, ["A"])["kill_criteria"], ["7"])

    def test_unknown_does_not_displace_facts_from_dossier(self):
        ev = [{"type": "UNKNOWN", "claim": "q%d" % i, "source": ""} for i in range(20)]
        ev += [{"type": "FACT", "claim": "the real fact", "source": "a.py:1"}]
        text = rt.dossier([("M1", ballot("A", evidence=ev))])
        self.assertIn("[FACT] the real fact", text)
        self.assertNotIn("[UNKNOWN]", text)
        self.assertIn("open questions (UNKNOWN, not evidence): q0; q1", text)

    def test_unknown_does_not_displace_facts_from_render(self):
        ev = [{"type": "UNKNOWN", "claim": "q%d" % i, "source": ""} for i in range(8)]
        ev += [{"type": "FACT", "claim": "the real fact", "source": "a.py:1"}]
        st = {"a": seat("A", evidence=ev), "b": seat("A"), "c": seat("B", evidence=ev)}
        md = rt.render(rt.build_result(meta(), st, OPTS))
        evidence_part = md.split("## Evidence for A")[1].split("## Unresolved")[0]
        self.assertEqual(evidence_part.count("the real fact"), 2)  # a's evidence and c's dissent
        self.assertNotIn("[UNKNOWN]", md)
        self.assertIn("## Unresolved questions", md)
        self.assertIn("- (c, voted B) q0", md)

    def test_kill_criteria_winning_side_only(self):
        st = {"a": seat("A", kill_criteria=["If p95 > 2s, reconsider"]), "b": seat("A"),
              "c": seat("B", kill_criteria=["If B fails"])}
        r = rt.build_result(meta(), st, OPTS)
        self.assertEqual(r["kill_criteria"], [{"seat": "a", "criterion": "If p95 > 2s, reconsider"}])
        self.assertEqual(r["kill_criteria_for"], "A")
        md = rt.render(r)
        self.assertIn("## Kill criteria for A (watch these", md)
        self.assertNotIn("If B fails", md)

    def test_kill_criteria_of_a_default_are_labelled(self):
        st = {"a": seat("A", kill_criteria=["If A breaks"]), "b": seat("B", kill_criteria=["If B breaks"])}
        r = rt.build_result(meta(default="B"), st, OPTS)
        self.assertEqual(r["tally"]["decided_by"], "default")
        md = rt.render(r)
        self.assertIn("## Kill criteria for B (safe default; from the seats that voted B, not a council choice)", md)
        self.assertNotIn("If A breaks", md)

    def test_no_quorum_without_default_has_no_kill_criteria(self):
        st = {"a": seat("A", kill_criteria=["If A breaks"]), "b": seat(None, status="unattended")}
        r = rt.build_result(meta(), st, OPTS)
        self.assertEqual((r["tally"]["verdict"], r["kill_criteria"], r["kill_criteria_for"]), (None, [], None))
        self.assertNotIn("Kill criteria", rt.render(r))

    def test_prompts_describe_the_new_fields(self):
        p1 = rt.prompt_round1("# q", OPTS, None, 3)
        for word in ("UNKNOWN", "kill_criteria", "restatement", "missing_option"):
            self.assertIn(word, p1)
        px = rt.prompt_cross("# q", OPTS, None, [("M1", ballot("A"))], 2, 2)
        self.assertIn("do not treat them as evidence when rating", px)
        self.assertIn("kill_criteria", px)


class FramingTest(unittest.TestCase):
    def framed(self, n, flagged):
        return {"s%d" % i: seat("A", missing_option="D: spike" if i < flagged else "") for i in range(n)}

    def test_thresholds(self):
        cases = [(2, 1, False), (2, 2, True), (3, 1, False), (3, 2, True), (5, 2, False), (5, 3, True),
                 (6, 2, False), (6, 3, True), (6, 4, True), (1, 1, False)]
        for n, k, want in cases:
            f = rt.build_result(meta(), self.framed(n, k), OPTS)["tally"]
            self.assertEqual(f["framing_concern"], want, (n, k))
            self.assertEqual(f["framing"]["threshold"], max(2, -(-n // 2)))

    def test_zero_valid_ballots_is_no_concern(self):
        st = {"a": seat("A", status="no_evidence", missing_option="D"), "b": seat("A", status="invalid", missing_option="D")}
        f = rt.build_result(meta(), st, OPTS)["tally"]["framing"]
        self.assertEqual((f["concern"], f["valid"]), (False, 0))

    def test_verdict_unchanged_by_framing(self):
        plain = rt.build_result(meta(), self.framed(4, 0), OPTS)["tally"]
        flagged = rt.build_result(meta(), self.framed(4, 4), OPTS)["tally"]
        self.assertTrue(flagged["framing_concern"])
        for k in ("verdict", "decided_by", "score", "count", "share"):
            self.assertEqual(plain[k], flagged[k])

    def test_reads_round_one_history_not_the_final_ballot(self):
        r1 = ballot("A", missing_option="D: spike", restatement="which db")
        st = {"a": seat("A", r1=r1), "b": seat("A", r1=r1)}  # final ballots have no missing_option
        r = rt.build_result(meta(), st, OPTS)
        self.assertTrue(r["tally"]["framing_concern"])
        md = rt.render(r)
        self.assertTrue(md.splitlines()[2].startswith("> **Framing concern (advisory):** 2 of 2"))
        self.assertIn("- (a) restated the question as: which db", md)

    def test_malformed_fields_are_coerced(self):
        b = rt.normalize_ballot({"vote": "A", "missing_option": True, "restatement": ["x", "y"]}, ["A"])
        self.assertEqual((b["missing_option"], b["restatement"]), ("", "x; y"))
        for empty in (None, False, "", " none ", "N/A", "-"):
            self.assertEqual(rt.normalize_ballot({"vote": "A", "missing_option": empty}, ["A"])["missing_option"], "")
        self.assertEqual(rt.normalize_ballot({"vote": "A", "missing_option": {"id": "D"}}, ["A"])["missing_option"], "{'id': 'D'}")

    def test_v01_state_without_new_fields(self):
        old = {"status": "ok", "ballot": {"vote": "A", "confidence": 0.5, "summary": "", "evidence": [{"type": "FACT", "claim": "x", "source": "y"}]},
               "history": [{"status": "ok", "ballot": {"vote": "A", "evidence": []}, "attempts": [{"model": "m", "status": "ok", "secs": 3}]}]}
        r = rt.build_result(meta(), {"a": old, "b": dict(old)}, OPTS)
        self.assertEqual((r["tally"]["verdict"], r["tally"]["framing_concern"], r["kill_criteria"]), ("A", False, []))
        self.assertEqual(r["usage"]["calls"], 2)
        rt.render(r)


class MinMarginTest(unittest.TestCase):
    def test_share_recorded_without_flag(self):
        r = rt.build_result(meta(), state_of("AAAABB"), OPTS)
        t = r["tally"]
        self.assertEqual((t["verdict"], t["share_of"], t["min_margin"], t["narrow_margin"]), ("A", "A", None, False))
        self.assertAlmostEqual(t["share"], 4 / 6)
        self.assertIn("Margin: A holds 0.667 of the valid weight.", rt.render(r))

    def test_four_two_passes_at_two_thirds_and_fails_at_067(self):
        st = state_of("AAAABB")
        ok = rt.build_result(meta(min_margin=rt.parse_share("2/3"), default="B"), st, OPTS)["tally"]
        self.assertEqual((ok["verdict"], ok["decided_by"], ok["narrow_margin"]), ("A", "council", False))
        r = rt.build_result(meta(min_margin=rt.parse_share("0.67"), default="B"), st, OPTS)
        miss = r["tally"]
        self.assertEqual((miss["verdict"], miss["decided_by"], miss["council_verdict"], miss["narrow_margin"]),
                         ("B", "default", "A", True))
        md = rt.render(r)
        self.assertIn("narrow margin: A leads with share 0.667 of the valid weight, below min-margin 0.670", md)
        self.assertIn("(safe default)", md)
        self.assertIn("## Evidence for B", md)  # sections follow the verdict acted on, as on a TIE

    def test_miss_without_default_is_none(self):
        t = rt.build_result(meta(min_margin=0.9), state_of("AAB"), OPTS)["tally"]
        self.assertEqual((t["verdict"], t["decided_by"], t["council_verdict"]), (None, "none", "A"))
        self.assertIn("narrow margin", rt.render(rt.build_result(meta(min_margin=0.9), state_of("AAB"), OPTS)))

    def test_three_way_plurality_below_half(self):
        # A3 B2 C1: share exactly 0.5, and the comparison is inclusive
        st = state_of("AAABBC")
        self.assertEqual(rt.build_result(meta(options=OPTS3, min_margin=0.5), st, OPTS3)["tally"]["decided_by"], "council")
        self.assertEqual(rt.build_result(meta(options=OPTS3, min_margin=0.51), st, OPTS3)["tally"]["narrow_margin"], True)
        # A2 B2 C2 without a tie-break seat: a TIE, not a narrow margin
        t = rt.build_result(meta(options=OPTS3, min_margin=0.3), state_of("AABBCC"), OPTS3)["tally"]
        self.assertEqual((t["verdict"], t["tie"], t["narrow_margin"]), (None, True, False))

    def test_fable_break_then_margin_miss_does_not_rebreak(self):
        st = {"fable": seat("B", tiebreak=True), "x": seat("B"), "y": seat("A"), "z": seat("A"), "u": seat("C"), "v": seat("C")}
        t = rt.build_result(meta(options=OPTS3), st, OPTS3)["tally"]
        self.assertEqual((t["verdict"], t["decided_by"]), ("B", "tiebreak"))
        self.assertAlmostEqual(t["share"], 1 / 3)
        t = rt.build_result(meta(options=OPTS3, min_margin=0.34, default="C"), st, OPTS3)["tally"]
        self.assertEqual((t["verdict"], t["decided_by"], t["council_verdict"]), ("C", "default", "B"))

    def test_two_option_tie_with_third_holding_weight(self):
        t = rt.build_result(meta(options=OPTS3, min_margin=0.1, default="C"), state_of("AABBC"), OPTS3)["tally"]
        self.assertEqual((t["verdict"], t["decided_by"], t["narrow_margin"]), ("C", "default", False))
        self.assertAlmostEqual(t["share"], 0.4)

    def test_count_rule_uses_weighted_share(self):
        st = {"a": seat("A", received=[0]), "b": seat("A", received=[0]), "c": seat("B", received=[2])}
        t = rt.build_result(meta(decision_rule="count"), st, OPTS)["tally"]
        self.assertEqual(t["verdict"], "A")
        self.assertAlmostEqual(t["share"], 1.0 / 2.5)

    def test_precedence_taint_and_quorum_first(self):
        t = rt.build_result(meta(min_margin=0.99, workspace_changed=True, default="B"), state_of("AAB"), OPTS)["tally"]
        self.assertEqual((t["verdict"], t["decided_by"], t["narrow_margin"]), (None, "workspace_changed", False))
        st = {"a": seat("A"), "b": seat(None, status="unattended")}
        t = rt.build_result(meta(min_margin=0.99, default="B"), st, OPTS)["tally"]
        self.assertEqual((t["no_quorum"], t["narrow_margin"], t["decided_by"]), (True, False, "default"))

    def test_parse_share(self):
        self.assertAlmostEqual(rt.parse_share("2/3"), 2 / 3)
        self.assertEqual((rt.parse_share("0.6"), rt.parse_share(1), rt.parse_share(None)), (0.6, 1.0, None))
        for bad in ("0", "1.5", "abc", "nan", "inf", "1/0", "-0.2", True):
            with self.assertRaises(SystemExit):
                rt.parse_share(bad)


class UsageUnitTest(unittest.TestCase):
    def test_counts(self):
        a = {"status": "ok", "level": 1, "history": [{"status": "ok", "attempts": [
            {"model": "p", "level": 0, "kind": "primary", "status": "quota", "secs": 2.0},
            {"model": "f", "level": 1, "kind": "fallback", "status": "invalid", "secs": 3.0},
            {"model": "f", "level": 1, "kind": "nudge", "status": "ok", "secs": 4.0}]}]}
        b = {"status": "unattended", "history": [{"status": "unattended", "attempts": [
            {"model": "x", "level": 0, "kind": "primary", "status": "missing", "secs": None}]}]}
        u = rt.compute_usage({"rounds": 2, "skipped": [{"id": "oc", "reason": "private"}],
                              "timing": {"rounds": {"r1": 9.5}, "rounds_run": 1, "total_secs": 11.0}}, {"a": a, "b": b})
        self.assertEqual((u["calls"], u["nudges"], u["fallback_calls"]), (3, 1, 2))
        self.assertEqual(u["per_seat"]["a"]["call_secs"], 9.0)
        self.assertEqual((u["unattended"], u["skipped"], u["fallback_seats"]), (["b"], ["oc"], ["a"]))
        self.assertEqual((u["rounds_requested"], u["rounds_run"], u["wall_secs"], u["total_wall_secs"]), (2, 1, {"r1": 9.5}, 11.0))

    def test_max_calls_formula(self):
        self.assertEqual([rt.seat_max_calls(2, r) for r in (1, 2, 3)], [4, 6, 8])
        self.assertEqual([rt.seat_max_calls(1, r) for r in (1, 2, 3)], [2, 4, 6])
        self.assertEqual(rt.seat_max_calls(0, 2), 0)


class E2EBase(unittest.TestCase):
    """Helpers for end-to-end runs through the CLI with fake seats; no tests of its own."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = dict(os.environ, ROUNDTABLE_RUNS=str(self.tmp / "runs"))
        self.env.pop("ROUNDTABLE_SEAT", None)

    def config(self, seats, extra=None, bin_=None):
        cfg = {"adapters": {"fake": {"bin": bin_ or sys.executable, "argv": [str(FAKE), "{model}"], "stdin": True}},
               "seats": seats, "presets": {"t": [s["id"] for s in seats]}}
        cfg.update(extra or {})
        (self.tmp / "cfg.json").write_text(json.dumps(cfg))
        (self.tmp / "brief.md").write_text(BRIEF)

    def cli(self, *argv, rc=None):
        p = subprocess.run([sys.executable, str(SCRIPT), "--config", str(self.tmp / "cfg.json"), *argv],
                           capture_output=True, text=True, env=self.env)
        if rc is not None:
            self.assertEqual(p.returncode, rc, p.stderr)
        return p

    def run_council(self, *extra, rc=0, out="run"):
        p = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--out", str(self.tmp / out),
                     "--seed", "1", "--timeout", "60", *extra, rc=rc)
        run = self.tmp / out
        return json.loads((run / "result.json").read_text()), (run / "decision.md").read_text(), p.stdout, run

    def status(self, run, *flags):
        return subprocess.run([sys.executable, str(SCRIPT), "status", str(run), *flags], capture_output=True, text=True)


class V02EndToEndTest(E2EBase):
    # --- usage
    def test_usage_counts_the_pre_nudge_call_and_survives_tally(self):
        self.config([{"id": "lazy", "adapter": "fake", "models": ["lazy-A"]},
                     {"id": "fb", "adapter": "fake", "models": ["quota", "vote-B"]},
                     {"id": "ok", "adapter": "fake", "models": ["vote-A"]},
                     {"id": "gone", "adapter": "fake", "models": ["quota", "unknown"]}])
        res, md, out, run = self.run_council("--rounds", "1")
        u = res["usage"]
        self.assertEqual(res["schema_version"], 2)
        self.assertEqual(u["per_seat"]["lazy"], dict(u["per_seat"]["lazy"], calls=2, nudges=1, fallback_calls=0))
        kinds = [a["kind"] for a in res["seats"]["lazy"]["history"][0]["attempts"]]
        self.assertEqual(kinds, ["primary", "nudge"])
        self.assertEqual((u["per_seat"]["fb"]["calls"], u["per_seat"]["fb"]["fallback_calls"]), (2, 1))
        self.assertEqual((u["calls"], u["nudges"], u["unattended"], u["rounds_run"]), (7, 1, ["gone"], 1))
        self.assertIn("r1", u["wall_secs"])
        self.assertIsNotNone(u["total_wall_secs"])
        self.assertIn("## Usage", md)
        self.assertIn("| lazy | 2 | 1 | 0 |", md)
        lines = out.rstrip().splitlines()
        self.assertTrue(lines[-2].startswith("MARGIN: ") and lines[-3].startswith("USAGE: 7 call(s)"))
        # re-tally keeps the recorded timings and counts, and the verdict
        self.cli("tally", str(run), rc=0)
        again = json.loads((run / "result.json").read_text())
        self.assertEqual(again["usage"], u)
        self.assertEqual(again["tally"]["verdict"], res["tally"]["verdict"])
        st = self.status(run)
        tail = st.stdout.rstrip().splitlines()
        self.assertEqual(tail[-2:], ["DONE", "VERDICT: %s (%s)" % (res["tally"]["verdict"], res["tally"]["decided_by"])])
        self.assertTrue(any(l.startswith("USAGE: ") for l in tail[:-2]))

    # --- dry run
    def test_dry_run_creates_nothing_and_calls_nobody(self):
        ws = make_repo()
        self.config([{"id": "a", "adapter": "fake", "models": ["write-A", "vote-A-9"]},
                     {"id": "b", "adapter": "fake", "models": ["write-B"]}])
        (self.tmp / "brief.md").write_text(BRIEF + "- C first and second together\n")
        p = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--workspace", str(ws),
                     "--out", str(self.tmp / "run"), "--dry-run", "--default", "b", "--min-margin", "2/3", "--deadline", "600", rc=0)
        plan = json.loads(p.stdout)
        self.assertFalse((self.tmp / "run").exists())
        self.assertFalse((self.tmp / "runs").exists())
        self.assertFalse((ws / "written-by-seat.txt").exists())
        self.assertEqual(p.stderr, "")
        self.assertEqual((plan["dry_run"], plan["default"], plan["rounds"], plan["sitting"], plan["quorum_ok"]), (True, "B", 2, 2, True))
        self.assertAlmostEqual(plan["min_margin"], 2 / 3)
        self.assertEqual([(s["id"], s["primary"], s["fallback"], s["max_calls"]) for s in plan["seats"]],
                         [("a", "write-A", "vote-A-9", 6), ("b", "write-B", None, 4)])
        self.assertEqual(plan["bounds"]["happy_path_calls"], 4)
        self.assertEqual(plan["bounds"]["max_calls"], 10)
        self.assertEqual(plan["bounds"]["max_wall_secs"], 600)  # 2 rounds x 4 calls x 60 s, capped by --deadline
        self.assertTrue(any("C first and second together" in w for w in plan["warnings"]))

    def test_dry_run_bounds_for_each_round_count(self):
        self.config([{"id": "a", "adapter": "fake", "models": ["vote-A", "vote-A-9"]}, {"id": "b", "adapter": "fake", "models": ["vote-B"]}])
        for rounds in (1, 2, 3):
            plan = json.loads(self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--rounds", str(rounds),
                                       "--timeout", "100", "--dry-run", rc=0).stdout)
            b = plan["bounds"]
            self.assertEqual(b["happy_path_calls"], 2 * rounds)
            self.assertEqual(b["max_calls"], rt.seat_max_calls(2, rounds) + rt.seat_max_calls(1, rounds))
            self.assertEqual(b["max_wall_secs"], rounds * (1 + rt.NUDGES) * 2 * 100)

    def test_dry_run_max_calls_is_reached_by_the_real_worst_case(self):
        # stall: no ballot, and the nudge crashes -> fallback; lazy: needs the nudge every round
        self.config([{"id": "w", "adapter": "fake", "models": ["stall", "lazy-A"]},
                     {"id": "x", "adapter": "fake", "models": ["vote-A"]}, {"id": "y", "adapter": "fake", "models": ["vote-A-2"]}])
        plan = json.loads(self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--dry-run", rc=0).stdout)
        res, _, _, _ = self.run_council()
        self.assertEqual(res["usage"]["per_seat"]["w"]["calls"], plan["seats"][0]["max_calls"])
        self.assertEqual(res["usage"]["per_seat"]["w"]["calls"], 6)

    def test_dry_run_private_reports_no_quorum(self):
        self.config([{"id": "gem", "adapter": "fake", "models": ["vote-A"]},
                     {"id": "oc", "adapter": "fake", "models": ["vote-B"], "may_train": True}])
        plan = json.loads(self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--private", "--dry-run", rc=0).stdout)
        self.assertEqual((plan["sitting"], plan["quorum_ok"]), (1, False))
        self.assertEqual(plan["skipped"][0]["id"], "oc")
        self.assertTrue(any(w.startswith("NO QUORUM") for w in plan["warnings"]))
        self.assertEqual(plan["bounds"]["happy_path_calls"], 1)

    def test_dry_run_reports_missing_cli(self):
        self.config([{"id": "a", "adapter": "fake", "models": ["vote-A"]}], bin_="definitely-not-a-cli-xyz")
        plan = json.loads(self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--dry-run", rc=0).stdout)
        self.assertEqual((plan["seats"][0]["cli_found"], plan["seats"][0]["can_sit"], plan["sitting"]), (False, False, 0))

    def test_dry_run_validation_matches_run(self):
        self.config([{"id": "a", "adapter": "fake", "models": ["vote-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-B"]}])
        for bad in (["--default", "Z"], ["--min-margin", "1.5"], ["--seats", "nope"], ["--deadline", "0"]):
            dry = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--dry-run", *bad)
            real = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--out", str(self.tmp / "run"), *bad)
            self.assertNotEqual(dry.returncode, 0, bad)
            self.assertEqual((dry.returncode, dry.stderr), (real.returncode, real.stderr), bad)
            self.assertFalse((self.tmp / "run").exists(), bad)

    def test_bad_seats_fail_before_detach(self):
        self.config([{"id": "a", "adapter": "fake", "models": ["vote-A"]}])
        p = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "nope", "--detach")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertIn("unknown seat or preset: nope", p.stderr)
        self.assertFalse((self.tmp / "runs").exists())

    # --- kill criteria, UNKNOWN, framing, status --json
    def test_kill_criteria_unknown_and_framing_reach_status_json(self):
        self.config([{"id": "fable", "adapter": "fake", "models": ["vote-A-kill-frame"], "tiebreak": True},
                     {"id": "opus", "adapter": "fake", "models": ["vote-A-unknown-frame-badkill"]},
                     {"id": "grok", "adapter": "fake", "models": ["vote-B-kill-restate"]},
                     {"id": "oc", "adapter": "fake", "models": ["vote-A-onlyunknown"]}])
        res, md, out, run = self.run_council()
        self.assertEqual(res["seats"]["oc"]["status"], "no_evidence")
        self.assertEqual(res["tally"]["verdict"], "A")
        self.assertEqual(res["kill_criteria"], [{"seat": "fable", "criterion": "If error rate > 1% is observed, reconsider A"},
                                                {"seat": "opus", "criterion": "{'if': 'x'}"}, {"seat": "opus", "criterion": "5"}])
        self.assertEqual(len(res["unresolved_questions"]), 6)  # opus's; oc's ballot does not count
        # round 2 ballots carry no framing fields; the check reads round 1
        self.assertEqual(res["seats"]["fable"]["ballot"]["missing_option"], "")
        self.assertTrue(res["tally"]["framing_concern"])
        self.assertEqual(res["tally"]["framing"]["valid"], 3)
        self.assertIn("## Kill criteria for A", md)
        self.assertNotIn("reconsider B", md)
        self.assertIn("> **Framing concern (advisory):** 2 of 3", md)
        self.assertEqual(out.rstrip().splitlines()[-1], "VERDICT: A (council)")
        st = self.status(run)
        tail = st.stdout.rstrip().splitlines()
        self.assertEqual(tail[-2:], ["DONE", "VERDICT: A (council)"])
        self.assertTrue(tail[-3].startswith("FRAMING: concern (2/3"))
        js = json.loads(self.status(run, "--json").stdout)
        self.assertEqual((js["state"], js["verdict"], js["decided_by"], js["actionable"], js["framing_concern"]),
                         ("DONE", "A", "council", True, True))
        self.assertEqual((js["kill_criteria_for"], len(js["kill_criteria"]), len(js["unresolved_questions"])), ("A", 3, 6))
        self.assertEqual((js["schema_version"], js["result_schema_version"]), (2, 2))

    # --- min margin
    def six(self):
        self.config([{"id": "s%d" % i, "adapter": "fake", "models": ["vote-%s-%d" % (v, i)]} for i, v in enumerate("AAAABB")])

    def test_min_margin_miss_falls_back_and_survives_tally(self):
        self.six()
        res, md, out, run = self.run_council("--rounds", "1", "--min-margin", "0.67", "--default", "b")
        t = res["tally"]
        self.assertEqual((t["verdict"], t["decided_by"], t["council_verdict"], t["narrow_margin"]), ("B", "default", "A", True))
        self.assertEqual(out.rstrip().splitlines()[-1], "VERDICT: B (default)")
        self.assertIn("narrow margin", md)
        self.assertEqual(json.loads((run / "meta.json").read_text())["min_margin"], 0.67)
        self.cli("tally", str(run), rc=0)
        again = json.loads((run / "result.json").read_text())["tally"]
        self.assertEqual((again["verdict"], again["council_verdict"], again["narrow_margin"]), ("B", "A", True))
        st = self.status(run).stdout.rstrip().splitlines()
        self.assertEqual(st[-2:], ["DONE", "VERDICT: B (default)"])
        self.assertIn("missed: narrow margin", st[-3])
        js = json.loads(self.status(run, "--json").stdout)
        self.assertEqual((js["verdict"], js["council_verdict"], js["narrow_margin"]), ("B", "A", True))

    def test_min_margin_two_thirds_passes_and_config_key(self):
        self.six()
        res, _, out, _ = self.run_council("--rounds", "1", "--min-margin", "2/3")
        self.assertEqual(out.rstrip().splitlines()[-1], "VERDICT: A (council)")
        self.config([{"id": "s%d" % i, "adapter": "fake", "models": ["vote-%s-%d" % (v, i)]} for i, v in enumerate("AAAABB")],
                    extra={"min_margin": 0.9})
        res, _, out, _ = self.run_council("--rounds", "1", out="run2")
        self.assertEqual((res["tally"]["narrow_margin"], res["meta"]["min_margin"]), (True, 0.9))
        self.assertEqual(out.rstrip().splitlines()[-1], "VERDICT: NONE (none)")

    # --- status --json for every state
    def test_status_json_tainted_failed_and_v01_result(self):
        ws = make_repo()
        self.config([{"id": "a", "adapter": "fake", "models": ["write-A"]}, {"id": "b", "adapter": "fake", "models": ["vote-A"]}])
        _, _, _, run = self.run_council("--rounds", "1", "--workspace", str(ws), rc=3)
        p = self.status(run, "--json")
        js = json.loads(p.stdout)
        self.assertEqual((p.returncode, js["state"], js["verdict"], js["decided_by"], js["actionable"]),
                         (4, "TAINTED", None, "workspace_changed", False))
        dead = self.tmp / "dead"
        dead.mkdir()
        (dead / "meta.json").write_text(json.dumps({"pid": 999999}))
        p = self.status(dead, "--json")
        self.assertEqual((p.returncode, json.loads(p.stdout)["state"], json.loads(p.stdout)["verdict"]), (1, "FAILED", None))
        old = self.tmp / "old"
        old.mkdir()
        (old / "meta.json").write_text("{}")
        (old / "decision.md").write_text("# old")
        (old / "result.json").write_text(json.dumps({"workspace_changed": False, "tally": {"verdict": "A", "decided_by": "council"}}))
        js = json.loads(self.status(old, "--json").stdout)
        self.assertEqual((js["state"], js["verdict"], js["result_schema_version"], js["framing_concern"], js["kill_criteria"]),
                         ("DONE", "A", 1, False, []))
        self.assertEqual(self.status(old).stdout.rstrip().splitlines()[-2:], ["DONE", "VERDICT: A (council)"])

    # --- deadline
    def test_deadline_cuts_calls_and_tallies_what_it_has(self):
        self.config([{"id": "a", "adapter": "fake", "models": ["slow", "vote-A"]},
                     {"id": "b", "adapter": "fake", "models": ["vote-A-2"]}, {"id": "c", "adapter": "fake", "models": ["vote-B-3"]},
                     {"id": "d", "adapter": "fake", "models": ["vote-A-4"]}])
        t0 = time.time()
        res, md, out, run = self.run_council("--deadline", "3")
        self.assertLess(time.time() - t0, 30)
        a = res["seats"]["a"]
        self.assertEqual(a["status"], "unattended")
        self.assertEqual([x["status"] for x in a["history"][0]["attempts"]], ["timeout"])  # fallback never started
        self.assertIn("run deadline", a["history"][0]["detail"])
        u = res["usage"]
        self.assertEqual((u["deadline_hit"], u["rounds_run"], u["deadline_secs"]), (True, 1, 3))
        self.assertEqual(res["tally"]["verdict"], "A")
        self.assertIn("r2 skipped: run deadline reached", (run / "progress.log").read_text())
        self.assertIn("run deadline reached", md)
        self.assertEqual(out.rstrip().splitlines()[-1], "VERDICT: A (council)")


if __name__ == "__main__":
    unittest.main()
