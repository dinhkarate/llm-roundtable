#!/usr/bin/env python3
"""Stand-in for an agent CLI. Behaviour comes from the model name:
  vote-X         answer with a ballot for X (with evidence)
  vote-X-bare    ballot for X without evidence
  vote-X-<flags> flags joined by "-" (unknown flags are ignored, e.g. vote-A-2 is just a distinct model id):
                   kill         adds kill_criteria
                   badkill      kill_criteria of the wrong shape (a dict and a number)
                   unknown      six UNKNOWN open questions listed before the FACT
                   onlyunknown  UNKNOWN items only (no FACT/INFERENCE)
                   frame        round 1: restatement + a missing_option (round 2 ballots carry neither)
                   restate      round 1: restatement only
  flip-X-Y       vote X in round 1, Y in cross-exam rounds
  quota          print a rate-limit error, exit 1
  unknown        print an unknown-model error, exit 1
  prose          answer without any JSON
  lazy-X         announce a plan without a ballot unless nudged, then vote X
  slow           sleep 60s (for timeout/stop tests)
  echo-quota     echo file text mentioning "quota" to stderr, then crash
  write-X        write a file into the cwd (breaks read-only), then vote X
  stall          no ballot; when nudged, crash (exit 1): worst case of one model call in _sit
Usage: fake_cli.py <model>   (prompt on stdin)
"""
import json
import re
import sys

model = sys.argv[1]
prompt = sys.stdin.read()
cross = "cross-examination" in prompt
labels = sorted(set(re.findall(r"^(M\d+) voted", prompt, re.M)))

if model == "quota":
    print("Error: You've hit your usage limit (429 Too Many Requests)", file=sys.stderr)
    sys.exit(1)
if model == "unknown":
    print("Couldn't set model 'x': unknown model id", file=sys.stderr)
    sys.exit(1)
if model == "slow":
    import time
    time.sleep(60)
    sys.exit(0)
if model == "echo-quota":
    print("reading tests: seats = [{'models': ['quota']}]\n" + "\n".join("line %d" % i for i in range(30)), file=sys.stderr)
    print("Error: connection reset", file=sys.stderr)
    sys.exit(1)
if model == "stall":
    if "previous attempt ended without a usable JSON ballot" in prompt:
        print("Error: connection reset", file=sys.stderr)
        sys.exit(1)
    print("Let me read the key files.")
    sys.exit(0)
if model == "prose":
    print("I think A is best.")
    sys.exit(0)

parts = model.split("-")
if parts[0] == "lazy" and "previous attempt ended without a usable JSON ballot" not in prompt:
    print("I'll review the files first, then vote.")
    sys.exit(0)
if parts[0] == "write":
    open("written-by-seat.txt", "w").write("x")
if parts[0] == "flip":
    vote, flags = (parts[2] if cross else parts[1]), set(parts[3:])
else:
    vote, flags = parts[1], set(parts[2:])
evidence = [{"type": "FACT", "claim": "fake fact", "source": "fake.txt:1"}]
if "bare" in flags:
    evidence = []
if "unknown" in flags:
    evidence = [{"type": "UNKNOWN", "claim": "open question %d" % i} for i in range(6)] + evidence
if "onlyunknown" in flags:
    evidence = [{"type": "UNKNOWN", "claim": "nobody knows", "source": "fake.txt:2"}]
ballot = {
    "vote": vote,
    "confidence": 0.7,
    "summary": "fake %s" % model,
    "evidence": evidence,
}
if "kill" in flags:
    ballot["kill_criteria"] = ["If error rate > 1%% is observed, reconsider %s" % vote]
if "badkill" in flags:
    ballot["kill_criteria"] = [{"if": "x"}, 5, "", None]
if not cross and ("frame" in flags or "restate" in flags):
    ballot["restatement"] = "pick between first and second"
    if "frame" in flags:
        ballot["missing_option"] = "D: run a two-week spike first"
if cross:
    # rate everyone 2 except members voting B, who get 0
    ratings = {}
    for lab in labels:
        m = re.search(r"^%s voted (\w+)" % lab, prompt, re.M)
        ratings[lab] = 0 if m and m.group(1) == "B" else 2
    ballot["ratings"] = ratings
print("analysis...\n```json\n%s\n```" % json.dumps(ballot))
