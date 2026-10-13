#!/usr/bin/env python3
"""Stand-in for an agent CLI. Behaviour comes from the model name:
  vote-X         answer with a ballot for X (with evidence)
  vote-X-bare    ballot for X without evidence
  flip-X-Y       vote X in round 1, Y in cross-exam rounds
  quota          print a rate-limit error, exit 1
  unknown        print an unknown-model error, exit 1
  prose          answer without any JSON
  lazy-X         announce a plan without a ballot unless nudged, then vote X
  write-X        write a file into the cwd (breaks read-only), then vote X
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
    vote = parts[2] if cross else parts[1]
else:
    vote = parts[1]
bare = parts[-1] == "bare"
ballot = {
    "vote": vote,
    "confidence": 0.7,
    "summary": "fake %s" % model,
    "evidence": [] if bare else [{"type": "FACT", "claim": "fake fact", "source": "fake.txt:1"}],
}
if cross:
    # rate everyone 2 except members voting B, who get 0
    ratings = {}
    for lab in labels:
        m = re.search(r"^%s voted (\w+)" % lab, prompt, re.M)
        ratings[lab] = 0 if m and m.group(1) == "B" else 2
    ballot["ratings"] = ratings
print("analysis...\n```json\n%s\n```" % json.dumps(ballot))
