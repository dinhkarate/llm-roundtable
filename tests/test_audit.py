"""--mode audit: findings in round 1, merged by the script, verified by the other seats in round 2.
Fake CLIs only (tests/fake_cli.py, models aud-<findings>-<policy>), no model calls."""
import json
import random
import unittest

import test_v02
from test_roundtable import make_repo, rt

AUDIT_BRIEF = "# Audit the login service\n\nLook for security and reliability problems in app.py and other.py.\n"


def finding(title, loc, sev="high", cat="security", typ="FACT"):
    return {"title": title, "severity": sev, "category": cat, "location": loc, "detail": "", "recommendation": "",
            "evidence": [{"type": typ, "claim": "c", "source": loc}], "supported": typ in rt.EVIDENCE_TYPES}


class AuditUnitTest(unittest.TestCase):
    def test_report_normalization(self):
        obj = {"summary": "s", "coverage": "c", "findings": [
            {"title": "A", "severity": "Moderate", "evidence": [{"type": "FACT", "claim": "x", "source": "a.py:1"}]},
            {"title": "B", "severity": "weird", "evidence": [{"type": "FACT", "claim": "x"}]},  # no source
            {"title": ""}, "junk"] + [{"title": "C%d" % i} for i in range(30)]}
        rep = rt.normalize_report(obj)
        self.assertEqual(rep["findings"][0]["severity"], "medium")
        self.assertTrue(rep["findings"][0]["supported"])
        self.assertEqual((rep["findings"][1]["severity"], rep["findings"][1]["supported"]), ("medium", False))
        self.assertLessEqual(len(rep["findings"]), rt.AUDIT_MAX_PER_SEAT)

    def test_classify_find_and_verify(self):
        r = rt.classify_audit({"rc": 0, "text": 'x {"findings": []}', "noise": ""}, "find")
        self.assertEqual((r["status"], r["ballot"]["findings"]), ("ok", []))
        text = ('{"verdicts": [{"id": "f1", "verdict": "confirmed", "evidence": [{"type": "FACT", "claim": "c", "source": "a.py:1"}]},'
                '{"id": "F2", "verdict": "REJECTED"}, {"id": "F9", "verdict": "CONFIRMED"}, {"id": "F1", "verdict": "REJECTED"}]}')
        v = rt.classify_audit({"rc": 0, "text": text, "noise": ""}, "verify", ["F1", "F2"])["ballot"]["verdicts"]
        self.assertEqual(v["F1"]["verdict"], "CONFIRMED")  # first answer per id wins
        self.assertEqual(v["F2"]["verdict"], "UNSURE")     # rejected without evidence
        self.assertNotIn("F9", v)                          # unknown id
        r = rt.classify_audit({"rc": 0, "text": '{"verdicts": []}', "noise": ""}, "verify", ["F1"])
        self.assertEqual(r["status"], "invalid")
        r = rt.classify_audit({"rc": 1, "text": "", "noise": "429 Too Many Requests"}, "find")
        self.assertEqual(r["status"], "quota")

    def test_same_finding(self):
        a = finding("SQL injection in login query", "app.py:2")
        self.assertTrue(rt.same_finding(a, finding("Login query builds SQL from user input", "app.py:3")))
        self.assertFalse(rt.same_finding(a, finding("Login query builds SQL from user input", "app.py:30")))
        self.assertFalse(rt.same_finding(a, finding("Missing request timeout", "app.py:3", cat="reliability")))
        self.assertTrue(rt.same_finding(a, finding("SQL injection in the login query", "db.py:9")))  # near-identical title

    def test_merge_never_joins_one_seats_findings_and_ids_are_seeded(self):
        a = finding("SQL injection in login query", "app.py:2")
        b = finding("SQL injection in login query form", "app.py:3")
        reports = [("s1", {"findings": [a, b]}), ("s2", {"findings": [finding("Login query builds SQL from input", "app.py:2")]}),
                   ("s3", {"findings": [finding("Unsupported", "x", typ="ASSUMPTION")]})]
        m1 = rt.merge_findings(reports, random.Random(1))
        self.assertEqual(sorted(len(f["reporters"]) for f in m1), [1, 2])  # s1's two findings stay apart
        self.assertEqual(len(m1), 2)                                       # unsupported finding left out
        m2 = rt.merge_findings(reports, random.Random(1))
        self.assertEqual([(f["id"], f["title"]) for f in m1], [(f["id"], f["title"]) for f in m2])

    def test_tally_rules(self):
        f = [dict(finding("t", "app.py:1"), id="F1", reporters=["a"], reported_severity={"a": "high"}, verify=True)]

        def st(verdicts):
            return {sid: {"status": "ok", "weight": 1.0, "history": [{"status": "ok"}, {"status": "ok", "ballot": {
                "kind": "verify", "verdicts": {"F1": {"verdict": v, "severity": "low", "note": "", "evidence": []}}}}]}
                for sid, v in verdicts.items()}

        def status(verdicts):
            return rt.audit_tally(f, st(verdicts))[0]["status"]
        self.assertEqual(status({"a": "REJECTED", "b": "CONFIRMED"}), "confirmed")  # a's own verdict ignored
        self.assertEqual(status({"b": "REJECTED", "c": "REJECTED"}), "rejected")
        self.assertEqual(status({"b": "REJECTED"}), "disputed")
        self.assertEqual(status({"b": "UNSURE"}), "unverified")
        self.assertEqual(status({"b": "CONFIRMED", "c": "CONFIRMED", "d": "REJECTED"}), "confirmed")
        self.assertEqual(rt.audit_tally(f, st({"b": "CONFIRMED"}))[0]["severity"], "low")  # lower median of high, low


class AuditEndToEndTest(test_v02.E2EBase):
    def setUp(self):
        super().setUp()
        self.ws = make_repo()
        (self.ws / "app.py").write_text("".join("line %d\n" % i for i in range(1, 11)))
        (self.ws / "other.py").write_text("a\nb\nc\n")

    def audit(self, models, *extra, rc=0):
        self.config([{"id": "s%d" % i, "adapter": "fake", "models": [m]} for i, m in enumerate(models)])
        (self.tmp / "brief.md").write_text(AUDIT_BRIEF)
        return self.run_council("--mode", "audit", "--workspace", str(self.ws), *extra, rc=rc)

    def by_title(self, res):
        return {f["title"]: f for f in res["findings"]}

    def test_merge_verify_confirm(self):
        res, md, out, run = self.audit(["aud-xy-conf", "aud-q-conf", "aud-0-rejy"])
        f = self.by_title(res)
        sql = f["Login query builds SQL from user input"]  # x and q merged, the critical wording leads
        self.assertEqual((sql["status"], sql["all_reporters"], sql["severity"]), ("confirmed", ["s0", "s1"], "high"))
        self.assertEqual(sql["support"], ["s0", "s1", "s2"])
        tmo = f["Missing request timeout"]
        self.assertEqual((tmo["status"], tmo["support"], tmo["against"]), ("confirmed", ["s0", "s1"], ["s2"]))
        self.assertEqual(res["tally"]["counts"]["confirmed"], 2)
        self.assertEqual(out.strip().splitlines()[-1], "VERDICT: FINDINGS (council)")
        self.assertIn("FINDINGS: 2 confirmed", out)
        self.assertIn("## Confirmed findings", md)
        self.assertEqual(len(json.loads((run / "findings.json").read_text())), 2)
        sj = json.loads(self.status(run, "--json").stdout)
        self.assertEqual((sj["verdict"], sj["audit"]["counts"]["confirmed"]), ("FINDINGS", 2))
        st = self.status(run).stdout.strip().splitlines()
        self.assertEqual(st[-2:], ["DONE", "VERDICT: FINDINGS (council)"])
        # tally replays the same statuses
        p = self.cli("tally", str(run), rc=0)
        self.assertEqual(p.stdout.strip().splitlines()[-1], "VERDICT: FINDINGS (council)")
        again = json.loads((run / "result.json").read_text())
        self.assertEqual([(x["id"], x["status"]) for x in again["findings"]], [(x["id"], x["status"]) for x in res["findings"]])

    def test_rejected_finding_gives_clean(self):
        res, md, out, run = self.audit(["aud-y-conf", "aud-0-rej", "aud-0-rej"])
        self.assertEqual(res["findings"][0]["status"], "rejected")
        self.assertEqual(out.strip().splitlines()[-1], "VERDICT: CLEAN (council)")

    def test_one_round_two_blind_reporters_confirm(self):
        res, md, out, run = self.audit(["aud-xy-conf", "aud-q-conf"], "--rounds", "1")
        f = self.by_title(res)
        self.assertEqual(f["Login query builds SQL from user input"]["status"], "confirmed")
        self.assertEqual(f["Missing request timeout"]["status"], "unverified")
        self.assertEqual(res["usage"]["rounds_run"], 1)

    def test_unsupported_and_ghost_sources_are_not_verified(self):
        res, md, out, run = self.audit(["aud-zny-conf", "aud-0-conf"])
        self.assertEqual([f["title"] for f in res["findings"]], ["Missing request timeout"])
        self.assertEqual(sorted(x["title"] for x in res["unsupported"]), ["Hardcoded key", "Vague concern"])
        self.assertTrue(res["downgraded_sources"])
        self.assertIn("## Findings without evidence", md)

    def test_verdicts_without_evidence_are_unsure(self):
        res, md, out, run = self.audit(["aud-y-conf", "aud-0-bare", "aud-0-bare"])
        f = res["findings"][0]
        self.assertEqual((f["status"], f["unsure"]), ("unverified", ["s1", "s2"]))
        self.assertEqual(out.strip().splitlines()[-1], "VERDICT: CLEAN (council)")

    def test_duplicates_fold_into_one_finding(self):
        res, md, out, run = self.audit(["aud-y-dupw", "aud-w-conf", "aud-0-dupw"])
        f = self.by_title(res)
        self.assertEqual(f["HTTP client never sets a deadline"]["status"], "duplicate")
        tmo = f["Missing request timeout"]
        self.assertEqual((tmo["status"], tmo["all_reporters"]), ("confirmed", ["s0", "s1"]))

    def test_quota_seat_is_dropped_and_no_quorum_is_none(self):
        res, md, out, run = self.audit(["aud-y-conf", "quota"])
        self.assertIn("s1", res["usage"]["unattended"])
        self.assertEqual(out.strip().splitlines()[-1], "VERDICT: NONE (none)")

    def test_failed_verifier_keeps_report(self):
        self.config([{"id": "s0", "adapter": "fake", "models": ["aud-y-conf"]},
                     {"id": "s1", "adapter": "fake", "models": ["aud-0-conf"]},
                     {"id": "s2", "adapter": "fake", "models": ["aud-0-none"]}])
        (self.tmp / "brief.md").write_text(AUDIT_BRIEF)
        res, md, out, run = self.run_council("--mode", "audit", "--workspace", str(self.ws))
        self.assertEqual(res["seats"]["s2"]["history"][1]["status"], "invalid")
        self.assertEqual(res["tally"]["verified_by"], ["s0", "s1"])
        self.assertEqual(res["findings"][0]["status"], "confirmed")

    def test_workspace_write_taints(self):
        res, md, out, run = self.audit(["aud-y-write", "aud-0-conf"], rc=3)
        self.assertEqual(out.strip().splitlines()[-1], "VERDICT: NONE (workspace_changed)")

    def test_default_refused_and_dry_run(self):
        self.config([{"id": "s0", "adapter": "fake", "models": ["aud-y-conf"]}])
        (self.tmp / "brief.md").write_text(AUDIT_BRIEF + "\n## Options\n- A: x\n- B: y\n")
        p = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--mode", "audit", "--default", "CLEAN")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--default does not apply", p.stderr)
        p = self.cli("run", "--brief", str(self.tmp / "brief.md"), "--seats", "t", "--mode", "audit", "--rounds", "3",
                     "--dry-run", rc=0)
        plan = json.loads(p.stdout)
        self.assertEqual((plan["mode"], plan["rounds"], plan["default"]), ("audit", 2, None))
        self.assertEqual([o[0] for o in plan["options"]], ["FINDINGS", "CLEAN"])
        self.assertTrue(any("ignores options" in w for w in plan["warnings"]))

    def test_ledger_counts_audits_without_shadow(self):
        self.audit(["aud-y-conf", "aud-0-conf"])
        s = rt.ledger_summary(self.tmp)
        self.assertEqual(s["runs"], 1)
        self.assertEqual(s["shadow"]["cross_examined_runs"], 0)


if __name__ == "__main__":
    unittest.main()
