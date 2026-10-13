#!/usr/bin/env python3
"""roundtable: a council of AI models from different vendors that gathers evidence,
cross-examines each other anonymously and votes with weighted ballots.

Every seat is an agentic CLI (claude, codex, grok, agy, opencode, ...) called headless and
read-only. The calling agent is only the moderator: it writes the brief, runs this script and
reports the verdict; it never votes.

Subcommands:
  run     convene the council on a brief and write decision.md + result.json
  doctor  show which seats can sit (CLI found, resolved models); --probe pings each model
  status  show progress of a run (for hosts that ran `run` in the background)
  tally   recompute the verdict from a finished run directory

Python 3.9+, stdlib only.
"""
import argparse
import atexit
import concurrent.futures as cf
import datetime as dt
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "seats.json"
USER_CONFIG = Path(os.environ.get("ROUNDTABLE_CONFIG", str(Path.home() / ".config/roundtable/seats.json")))
RUNS_DIR = Path(os.environ.get("ROUNDTABLE_RUNS", str(Path.home() / ".roundtable/runs"))).expanduser().resolve()
MODELS_DEV = "https://models.dev/api.json"
DEAD_FILE = RUNS_DIR.parent / "dead-models.json"

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
QUOTA_RE = re.compile(
    r"rate.?limit|quota|usage limit|too many requests|\b429\b|insufficient (credit|balance|funds)|"
    r"credit balance|limit (reached|exceeded)|resource.?exhausted|overloaded|out of credits|try again (later|in)",
    re.I,
)
UNAVAILABLE_RE = re.compile(
    r"unknown model|unrecognized_model|model .{0,40}not supported|is not supported|isn't described|"
    r"has been deprecated|model not found|no such model|invalid model|may not exist|"
    r"not available|couldn't set model|unknown model id",
    re.I,
)
SECRET_RES = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
]
REVIEW_OPTIONS = [
    ("APPROVE", "Approve as is"),
    ("CHANGES", "Approve only after the listed changes"),
    ("REJECT", "Reject"),
]
FALLBACK_STATUSES = {"quota", "unavailable", "error", "timeout"}
EVIDENCE_TYPES = {"FACT", "INFERENCE"}

_log_lock = threading.Lock()
_live = set()  # Popen objects of running seats, reaped on exit/signal


def _kill_tree(p):
    try:
        if os.name != "nt":
            os.killpg(p.pid, signal.SIGKILL)  # agent CLIs spawn children; kill the whole tree
        else:
            p.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def reap_all(*_):
    for p in list(_live):
        _kill_tree(p)


def _on_signal(signum, _frame):
    reap_all()
    sys.exit(128 + signum)


# ---------------------------------------------------------------- config

def load_config(path=None):
    cfg = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    user = Path(path) if path else USER_CONFIG
    if user.exists():
        over = json.loads(user.read_text(encoding="utf-8"))
        for key in ("adapters", "presets"):
            cfg[key].update(over.get(key, {}))
        by_id = {s["id"]: s for s in cfg["seats"]}
        for s in over.get("seats", []):
            if s["id"] in by_id:
                by_id[s["id"]].update(s)
            else:
                cfg["seats"].append(s)
        for key, val in over.items():
            if key not in ("adapters", "presets", "seats"):
                cfg[key] = val
    return cfg


def remember_dead(model):
    """Models a CLI reported as deprecated; auto-selection skips them next time."""
    with _log_lock:
        dead = set(json.loads(DEAD_FILE.read_text(encoding="utf-8"))) if DEAD_FILE.exists() else set()
        dead.add(model)
        DEAD_FILE.parent.mkdir(parents=True, exist_ok=True)
        DEAD_FILE.write_text(encoding="utf-8", data=json.dumps(sorted(dead)))


def models_dev_opencode():
    """Release dates of opencode models from models.dev, cached for a day (stale cache beats nothing)."""
    cache = RUNS_DIR.parent / "models-dev-opencode.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        req = urllib.request.Request(MODELS_DEV, headers={"User-Agent": "roundtable/1 (+https://github.com/dinhkarate/roundtable)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            meta = json.load(r).get("opencode", {}).get("models", {})
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(encoding="utf-8", data=json.dumps(meta))
        return meta
    except Exception as e:
        print("warning: models.dev unavailable (%s); opencode models ordered without release dates" % e, file=sys.stderr)
        return json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}


def opencode_free_models(exclude):
    """Free opencode models this host can call, newest first (release dates from models.dev)."""
    if not shutil.which("opencode"):
        return []
    listed = []
    # the background service sometimes answers with an empty list for a few seconds (e.g. right after
    # an `opencode run` exits); --standalone is no help, it lists no providers at all
    for attempt in range(4):
        if attempt:
            time.sleep(3)
        try:
            out = subprocess.run(["opencode", "models"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 stdin=subprocess.DEVNULL, timeout=90).stdout
        except (subprocess.SubprocessError, OSError):
            continue
        listed = [l.strip() for l in out.splitlines() if l.strip().startswith("opencode/")]
        if listed:
            break
    meta = models_dev_opencode()
    dead = set(json.loads(DEAD_FILE.read_text(encoding="utf-8"))) if DEAD_FILE.exists() else set()
    ex = re.compile(exclude, re.I) if exclude else None
    rows = []
    for full in listed:
        mid = full.split("/", 1)[1]
        m = meta.get(mid, {})
        free = "free" in mid or (m.get("cost") or {}).get("input") == 0
        if not free or m.get("status") == "deprecated" or full in dead:
            continue
        if ex and (ex.search(mid) or ex.search(str(m.get("family") or ""))):
            continue
        rows.append((m.get("release_date") or "0000", full))
    rows.sort(reverse=True)
    return [full for _, full in rows]


def resolve_seats(cfg, names, private=False):
    """Expand the requested seat ids into concrete seats with a model chain of length <= 2."""
    wanted = []
    for n in names:
        wanted.extend(cfg["presets"].get(n, [n]))
    seen, order = set(), []
    for n in wanted:
        if n not in seen:
            seen.add(n)
            order.append(n)
    by_id = {s["id"]: s for s in cfg["seats"]}
    seats, skipped = [], []
    for sid in order:
        if sid not in by_id:
            raise SystemExit("unknown seat or preset: %s (known: %s)" % (sid, ", ".join(list(by_id) + list(cfg["presets"]))))
        s = dict(by_id[sid])
        if private and s.get("may_train"):
            skipped.append({"id": sid, "reason": "skipped by --private (provider may train on prompts)"})
            continue
        models = s["models"]
        if isinstance(models, str) and models.startswith("auto:opencode-free"):
            count = int(s.get("count", 1))
            cands = opencode_free_models(s.get("exclude", ""))
            for i in range(count):
                seat = dict(s)
                seat["id"] = sid if count == 1 else "%s-%d" % (sid, i + 1)
                seat["models"] = [m for m in (cands[i:i + 1] + cands[i + count:i + count + 1])]
                if not seat["models"]:
                    seat["unresolved"] = "no free opencode model found"
                seats.append(seat)
        else:
            s["models"] = list(models)[:2]  # primary + one fallback level, never more
            seats.append(s)
    # a fallback that is another seat's primary would make two seats the same voice: drop it
    primaries = {(s["adapter"], s["models"][0]) for s in seats if s["models"]}
    for s in seats:
        if len(s["models"]) == 2 and (s["adapter"], s["models"][1]) in primaries:
            s["fallback_dropped"] = s["models"].pop()
    return seats, skipped


# ---------------------------------------------------------------- calling a seat

def log(run_dir, msg):
    line = "%s %s" % (dt.datetime.now().strftime("%H:%M:%S"), msg)
    with _log_lock:
        with open(run_dir / "progress.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line, file=sys.stderr, flush=True)


PLACEHOLDER_RE = re.compile(r"\{(model|prompt|prompt_file|out_file)\}")


def fill(template, values):
    """One pass, so a placeholder inside a substituted value (e.g. the prompt text) stays literal."""
    return PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def call_cli(adapter, model, prompt, seat_dir, cwd, timeout, seat_id):
    seat_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = seat_dir / "prompt.md"
    out_file = seat_dir / "last_message.txt"
    prompt_file.write_text(encoding="utf-8", data=prompt)
    if out_file.exists():
        out_file.unlink()
    exe = shutil.which(adapter["bin"])
    if not exe:
        return {"status": "missing", "detail": "%s not on PATH" % adapter["bin"], "text": ""}
    values = {"model": model, "prompt": prompt, "prompt_file": str(prompt_file), "out_file": str(out_file)}
    argv = [exe] + [fill(a, values) for a in adapter["argv"]]
    env = dict(os.environ, ROUNDTABLE_SEAT=seat_id, NO_COLOR="1")
    start = time.time()
    stdin = open(prompt_file, encoding="utf-8") if adapter.get("stdin") else subprocess.DEVNULL
    kw = {"start_new_session": True} if os.name != "nt" else {}
    try:
        p = subprocess.Popen(argv, cwd=str(cwd), stdin=stdin, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8", errors="replace", **kw)
        _live.add(p)
        try:
            out, err = p.communicate(timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            _kill_tree(p)
            out, err = p.communicate()
            rc = None
        finally:
            _live.discard(p)
    finally:
        if stdin is not subprocess.DEVNULL:
            stdin.close()
    secs = round(time.time() - start, 1)
    (seat_dir / "stdout.txt").write_text(encoding="utf-8", data=out or "")
    (seat_dir / "stderr.txt").write_text(encoding="utf-8", data=err or "")
    text = out or ""
    if adapter.get("output") == "out_file" and out_file.exists():
        text = out_file.read_text(encoding="utf-8")
    res = {"rc": rc, "secs": secs, "text": ANSI_RE.sub("", text), "noise": ANSI_RE.sub("", (out or "") + "\n" + (err or ""))}
    if rc is None:
        res["status"] = "timeout"
        res["detail"] = "no answer after %ss" % timeout
    return res


def parse_ballot(text, option_ids=None):
    """The last top-level JSON object in text with a "vote" key, preferring one whose vote is a valid option.
    Objects nested inside another (e.g. a rebuttal quoting {"vote": ...}) are never picked."""
    dec = json.JSONDecoder()
    top, i = [], text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(obj, dict) and "vote" in obj:
            top.append(obj)
        i = text.find("{", end)
    for obj in reversed(top):
        if not option_ids or str(obj["vote"]).strip().upper() in option_ids:
            return obj
    return top[-1] if top else None


def _list(x):
    return x if isinstance(x, list) else ([] if x in (None, "") else [x])


def _num(x, default):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if v == v and v not in (float("inf"), float("-inf")) else default


def normalize_ballot(obj, option_ids):
    """Coerce whatever the model returned into a ballot; malformed fields are dropped, never raised."""
    vote = str(obj.get("vote", "")).strip().upper()
    if vote not in option_ids:
        m = re.match(r"^\(?([A-Z0-9_]+)\)?\b", vote)
        vote = m.group(1) if m and m.group(1) in option_ids else None
    evidence = []
    for e in _list(obj.get("evidence")):
        if not isinstance(e, dict) or not str(e.get("claim", "")).strip():
            continue
        etype = str(e.get("type", "ASSUMPTION")).strip().upper()
        source = str(e.get("source", "") or "").strip()
        if etype in EVIDENCE_TYPES and not source:
            etype = "ASSUMPTION"  # a fact or inference nobody can trace is an assumption
        evidence.append({"type": etype, "claim": str(e["claim"]).strip(), "source": source})
    ratings = {}
    raw = obj.get("ratings")
    if isinstance(raw, dict):
        for k, v in raw.items():
            n = _num(v, None)
            if n is not None:
                ratings[str(k).strip().upper()] = max(0, min(2, int(round(n))))
    return {
        "vote": vote,
        "confidence": max(0.0, min(1.0, _num(obj.get("confidence"), 0.5))),
        "summary": str(obj.get("summary", "") or "").strip(),
        "evidence": evidence,
        "risks": [str(x) for x in _list(obj.get("risks"))],
        "conditions": [str(x) for x in _list(obj.get("conditions"))],
        "rebuttals": [r for r in _list(obj.get("rebuttals")) if isinstance(r, dict)],
        "ratings": ratings,
        "decisive_evidence": [str(x) for x in _list(obj.get("decisive_evidence"))],
    }


def classify(res, option_ids):
    if res.get("status") in ("missing", "timeout"):
        return res
    obj = parse_ballot(res["text"], option_ids) or (parse_ballot(res["noise"], option_ids) if res.get("rc") == 0 else None)
    if obj is not None:
        ballot = normalize_ballot(obj, option_ids)
        res["ballot"] = ballot
        if ballot["vote"] is None:
            res["status"], res["detail"] = "invalid", "vote is not one of %s" % ",".join(option_ids)
        elif not any(e["type"] in EVIDENCE_TYPES for e in ballot["evidence"]):
            res["status"], res["detail"] = "no_evidence", "ballot has no FACT/INFERENCE evidence"
        else:
            res["status"] = "ok"
        return res
    tail = res["noise"][-4000:]
    if UNAVAILABLE_RE.search(tail):
        res["status"] = "unavailable"
    elif QUOTA_RE.search(tail):
        res["status"] = "quota"
    elif res.get("rc") not in (0, None):
        res["status"] = "error"
    else:
        res["status"] = "invalid"
    lines = [l for l in tail.strip().splitlines() if l.strip()]
    res["detail"] = (lines[-1] if lines else "no output")[:300]
    return res


def sit(seat, cfg, prompt, rnd_dir, cwd, timeout, option_ids, run_dir, rnd, start_at=0):
    """Never raises: a crash inside one seat must not take the council down."""
    try:
        return _sit(seat, cfg, prompt, rnd_dir, cwd, timeout, option_ids, run_dir, rnd, start_at)
    except Exception as e:  # noqa: BLE001
        log(run_dir, "r%d %-10s crashed: %r" % (rnd, seat["id"], e))
        return {"status": "unattended", "detail": "orchestrator error: %r" % e, "attempts": []}


def _sit(seat, cfg, prompt, rnd_dir, cwd, timeout, option_ids, run_dir, rnd, start_at=0):
    """Ask one seat, walking its model chain (primary -> one fallback) on quota/unavailable/error."""
    attempts = []
    adapter = cfg["adapters"].get(seat["adapter"])
    if seat.get("unresolved") or adapter is None:
        detail = seat.get("unresolved") or "no adapter %s" % seat["adapter"]
        log(run_dir, "r%d %-10s %-24s %-11s %s" % (rnd, seat["id"], "-", "unattended", detail))
        return {"status": "unattended", "detail": detail, "attempts": attempts}
    for i, model in enumerate(seat["models"]):
        if i < start_at:
            continue
        res = call_cli(adapter, model, prompt, rnd_dir / seat["id"] / str(i), cwd, timeout, seat["id"])
        res = classify(res, option_ids)
        if res["status"] == "invalid":
            # agent CLIs sometimes end the turn early (a tool was denied, it only announced a plan) or emit
            # broken JSON: one nudge, same model, not counted as a fallback
            log(run_dir, "r%d %-10s %-24s %-11s %ss retrying once: %s" % (rnd, seat["id"], model, "invalid", res.get("secs"), res.get("detail", "")[:120]))
            nudge = (prompt + "\n\nIMPORTANT: a previous attempt ended without a usable JSON ballot (%s; it ended with: %r). "
                     "If a tool or command is not permitted, continue without it. Do not stop until you have "
                     "printed the fenced JSON block: valid JSON, with \"vote\" exactly one of %s."
                     % (res.get("detail", ""), res["text"].strip()[-300:], ", ".join(option_ids)))
            res = classify(call_cli(adapter, model, nudge, rnd_dir / seat["id"] / ("%d-retry" % i), cwd, timeout, seat["id"]), option_ids)
        res["model"], res["level"] = model, i
        if res["status"] == "unavailable" and "deprecated" in res.get("detail", "").lower():
            remember_dead(model)
        attempts.append({k: res.get(k) for k in ("model", "status", "detail", "secs")})
        log(run_dir, "r%d %-10s %-24s %-11s %ss %s" % (rnd, seat["id"], model, res["status"], res.get("secs", "-"),
                                                       res.get("detail", "") if res["status"] != "ok" else ""))
        if res["status"] == "missing":
            break
        if res["status"] not in FALLBACK_STATUSES:
            res["attempts"] = attempts
            return res
    last = attempts[-1] if attempts else {}
    return {"status": "unattended", "detail": "; ".join("%s: %s" % (a["model"], a["status"]) for a in attempts) or last.get("detail", ""),
            "attempts": attempts}


# ---------------------------------------------------------------- prompts

BALLOT_SCHEMA_R1 = """```json
{"vote": "<option id>", "confidence": 0.0, "summary": "<2-4 sentences: why>",
 "evidence": [{"type": "FACT|INFERENCE|ASSUMPTION", "claim": "<what>", "source": "<file:line, command, URL, doc>"}],
 "risks": ["<risk of your choice>"], "conditions": ["<what must hold for your choice to stay right>"]}
```"""

BALLOT_SCHEMA_RX = """```json
{"vote": "<option id>", "confidence": 0.0, "summary": "<2-4 sentences: why, after cross-examination>",
 "evidence": [{"type": "FACT|INFERENCE|ASSUMPTION", "claim": "<what>", "source": "<file:line, command, URL, doc>"}],
 "rebuttals": [{"member": "M2", "point": "<the flaw or counter-evidence>", "source": "<where>"}],
 "ratings": {"M1": 2, "M2": 0},
 "decisive_evidence": ["<member + claim that decided your vote>"],
 "risks": ["..."], "conditions": ["..."]}
```"""


def options_block(options):
    return "\n".join("- %s: %s" % (oid, label) for oid, label in options)


def access_note(workspace):
    if workspace:
        return ("You may READ files under the current working directory and run read-only commands "
                "(ls, cat, grep, git log/show/diff) to verify claims. You may use web search if your tools allow.")
    return ("You cannot see the user's files. Rely on the brief, your own knowledge and web sources "
            "if your tools allow.")


def prompt_round1(brief, options, workspace, n_members):
    return f"""You are one member of a decision council ("roundtable") of {n_members} AI models from different vendors.
Each member answers the same brief independently; you will not see the others in this round.

Rules
- Strictly read-only: do not create, edit or delete files, do not change any system, do not call any council/roundtable skill or spawn other agents.
- {access_note(workspace)}
- Gather evidence BEFORE concluding. Label every item:
  FACT = verified, with a concrete source (file:line, command output, URL + quote, official doc, benchmark, known incident);
  INFERENCE = reasoned from facts you cite; ASSUMPTION = unverified belief.
  A ballot without at least one FACT or INFERENCE item is discarded.
- Choose exactly one option id. If none is fully acceptable, choose the least bad and put what must change in "conditions".
- Prefer being right over being agreeable. Write prose in the language of the brief.

=== BRIEF ===
{brief.strip()}

=== OPTIONS ===
{options_block(options)}

Answer: a short analysis, then END with exactly one fenced JSON block:
{BALLOT_SCHEMA_R1}
"""


def redact(text):
    for rx in SECRET_RES:
        text = rx.sub("[REDACTED]", text)
    return text


def dossier(positions):
    parts = []
    for label, b in positions:
        ev = "\n".join("    - [%s] %s (source: %s)" % (e["type"], e["claim"][:500], e["source"][:200] or "none")
                       for e in b["evidence"][:12]) or "    - (none)"
        extra = ""
        if b.get("rebuttals"):
            extra = "\n  rebuttals:\n" + "\n".join("    - vs %s: %s" % (r.get("member", "?"), str(r.get("point", ""))[:400])
                                                    for r in b["rebuttals"][:6])
        parts.append("%s voted %s (confidence %.2f)\n  summary: %s\n  evidence:\n%s%s"
                     % (label, b["vote"], b["confidence"], b["summary"][:1200], ev, extra))
    return "\n\n".join(parts)


def prompt_cross(brief, options, workspace, positions, rnd, total, redact_fn=None):
    labels = ", ".join(l for l, _ in positions)
    return f"""You are one member of a decision council ("roundtable"). Round {rnd} of {total}: cross-examination.
Below are the brief and the positions of ALL members from the previous round, anonymized as {labels}.
One of them may be your own earlier answer; identities are hidden on purpose, judge only the evidence.

Rules
- Strictly read-only, as before. Do not call any council/roundtable skill or spawn other agents.
- {access_note(workspace)}
- For each member, check the evidence (verify what you can) and rate it in "ratings":
  0 = unsupported or wrong, 1 = plausible but thin or unverified, 2 = specific and verified.
- For every position you disagree with, give the strongest concrete flaw or counter-evidence in "rebuttals".
- Then vote again. Vote counts and confidence are NOT evidence: do not follow the majority. Switch only when a
  specific evidence item compels it, and name it in "decisive_evidence".
- Your ballot needs at least one FACT or INFERENCE evidence item. Write prose in the language of the brief.

=== BRIEF ===
{brief.strip()}

=== OPTIONS ===
{options_block(options)}

=== POSITIONS FROM THE PREVIOUS ROUND ===
{(redact_fn or (lambda t: t))(dossier(positions))}

Answer: a short critique, then END with exactly one fenced JSON block:
{BALLOT_SCHEMA_RX}
"""


# ---------------------------------------------------------------- tally

def tally(seats_state, options, decision_rule="weighted"):
    """seats_state: {seat_id: {"ballot":..., "status":..., "weight":..., "tiebreak":..., "label":..., "ratings_received":[...]}}"""
    option_ids = [o for o, _ in options]
    score = {o: 0.0 for o in option_ids}
    count = {o: 0 for o in option_ids}
    voters = {o: [] for o in option_ids}
    rows = []
    for sid, st in seats_state.items():
        b = st.get("ballot")
        valid = st.get("status") == "ok" and b and b.get("vote") in score
        received = st.get("ratings_received") or []
        peer = sum(received) / len(received) if received else 1.0
        weight = st.get("weight", 1.0) * (0.5 + 0.5 * peer) if valid else 0.0
        if valid:
            score[b["vote"]] += weight
            count[b["vote"]] += 1
            voters[b["vote"]].append(sid)
        rows.append({"seat": sid, "vote": b.get("vote") if b else None, "valid": bool(valid),
                     "peer_score": round(peer, 2) if received else None, "weight": round(weight, 3)})
    n_valid = sum(count.values())
    key = (lambda o: (score[o], count[o])) if decision_rule == "weighted" else (lambda o: (count[o], score[o]))
    ranked = sorted(option_ids, key=key, reverse=True)
    top = ranked[0]
    if decision_rule == "weighted":
        tied = [o for o in option_ids if abs(score[o] - score[top]) < 1e-9]
    else:
        tied = [o for o in option_ids if count[o] == count[top] and abs(score[o] - score[top]) < 1e-9]
    verdict, tiebreak = top, None
    if len(tied) > 1:
        breakers = [sid for sid, st in seats_state.items() if st.get("tiebreak") and st.get("status") == "ok"
                    and st.get("ballot") and st["ballot"].get("vote") in tied]
        if breakers:
            verdict = seats_state[breakers[0]]["ballot"]["vote"]
            tiebreak = "tie between %s broken by %s" % ("/".join(tied), breakers[0])
        else:
            verdict, tiebreak = None, "tie between %s; no tie-break seat voted for one of them" % "/".join(tied)
    return {"verdict": verdict, "tie": len(tied) > 1, "tiebreak": tiebreak, "valid_votes": n_valid,
            "score": {o: round(score[o], 3) for o in option_ids}, "count": count, "voters": voters, "rows": rows,
            "total_weight": round(sum(score.values()), 3)}


# ---------------------------------------------------------------- run

def slugify(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "decision"


def parse_options(args, brief):
    opts = []
    for o in args.option or []:
        if "=" not in o:
            raise SystemExit("--option must look like A='text'")
        k, v = o.split("=", 1)
        opts.append((k.strip().upper(), v.strip()))
    if not opts:
        m = re.search(r"^#+\s*Options\s*$(.*?)(?=^#+\s|\Z)", brief, re.M | re.S | re.I)
        if m:
            for line in m.group(1).splitlines():
                mm = re.match(r"^\s*[-*]\s*\**([A-Za-z0-9_]+)\**\s*[:.)\-–]\s*(.+)$", line)
                if mm:
                    opts.append((mm.group(1).upper(), mm.group(2).strip()))
    if not opts and args.mode == "review":
        opts = list(REVIEW_OPTIONS)
    if len(opts) < 2:
        raise SystemExit("need at least 2 options: add a '## Options' section (- A: ...) to the brief or pass --option A='...'")
    return opts


def secret_scan(text):
    hits = []
    for rx in SECRET_RES:
        for m in rx.finditer(text):
            hits.append(m.group(0)[:6] + "…")
    return hits


def cmd_run(args):
    if os.environ.get("ROUNDTABLE_SEAT"):
        raise SystemExit("refusing to convene a council from inside a council seat (ROUNDTABLE_SEAT=%s)" % os.environ["ROUNDTABLE_SEAT"])
    cfg = load_config(args.config)
    brief = Path(args.brief).read_text(encoding="utf-8") if args.brief != "-" else sys.stdin.read()
    options = parse_options(args, brief)
    option_ids = [o for o, _ in options]
    hits = secret_scan(brief + "\n" + options_block(options) + "\n" + (args.title or ""))
    if hits and not args.allow_sensitive:
        raise SystemExit("brief or options look like they contain secrets (%s). Remove them; they are sent to several "
                         "vendors. Use --allow-sensitive only if these are false positives." % ", ".join(hits))
    rounds = max(1, min(3, args.rounds or cfg.get("rounds", 2)))
    timeout = args.timeout or cfg.get("timeout", 900)
    title = args.title or (brief.strip().splitlines() or ["decision"])[0].lstrip("# ").strip()
    run_dir = Path(args.out).resolve() if args.out else RUNS_DIR / ("%s-%s" % (dt.datetime.now().strftime("%Y%m%d-%H%M%S"), slugify(title)))
    run_dir.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now().isoformat(timespec="seconds")
    # meta first, so `status` sees this run (STARTING) while seats resolve (opencode discovery can take a while)
    (run_dir / "meta.json").write_text(encoding="utf-8", data=json.dumps({"title": title, "started": started, "pid": os.getpid()}))
    print(str(run_dir), flush=True)
    (run_dir / "brief.md").write_text(encoding="utf-8", data=brief)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _on_signal)
    atexit.register(reap_all)
    seats, skipped = resolve_seats(cfg, (args.seats or "full").split(","), private=args.private)
    workspace = Path(args.workspace).resolve() if args.workspace else None
    meta = {"title": title, "options": options, "rounds": rounds, "timeout": timeout, "mode": args.mode,
            "workspace": str(workspace) if workspace else None, "private": args.private,
            "decision_rule": cfg.get("decision_rule", "weighted"), "quorum": cfg.get("quorum", 2),
            "seats": seats, "skipped": skipped, "started": started, "pid": os.getpid()}
    (run_dir / "meta.json").write_text(encoding="utf-8", data=json.dumps(meta, indent=2, ensure_ascii=False))
    log(run_dir, "council: %s | options %s | rounds %d" % (", ".join(s["id"] for s in seats), ",".join(option_ids), rounds))

    # seat working dirs live outside run_dir so a seat cannot read the label map or other seats' transcripts
    scratch = Path(tempfile.mkdtemp(prefix="roundtable-"))
    atexit.register(shutil.rmtree, str(scratch), True)
    snapshot = {}

    def seat_cwd(seat):
        isolate = cfg["adapters"].get(seat["adapter"], {}).get("isolate")
        if workspace and not isolate:
            return workspace
        d = scratch / seat["id"]
        if not d.exists():
            d.mkdir(parents=True)
            if workspace and isolate:
                ok = snapshot_workspace(workspace, d)
                snapshot[seat["id"]] = bool(ok)
                log(run_dir, "%s reads a snapshot copy of the workspace (its CLI cannot be made read-only)%s"
                    % (seat["id"], "" if ok else ": snapshot unavailable (not git or too large), seat sees no files"))
        return d

    state = {s["id"]: {"seat": s, "weight": s.get("weight", 1.0), "tiebreak": bool(s.get("tiebreak")),
                       "history": [], "level": 0} for s in seats}

    fp_before = workspace_fingerprint(workspace)

    # round 1: independent
    p1 = prompt_round1(brief, options, workspace, len(seats))
    with cf.ThreadPoolExecutor(max_workers=max(1, len(seats))) as ex:
        futs = {ex.submit(sit, s, cfg, p1, run_dir / "r1", seat_cwd(s), timeout, option_ids, run_dir, 1): s for s in seats}
        for f in cf.as_completed(futs):
            s = futs[f]
            res = f.result()
            st = state[s["id"]]
            st["history"].append(slim(res))
            st["status"], st["ballot"], st["model"] = res["status"], res.get("ballot"), res.get("model")
            st["level"] = res.get("level", 0)

    # cross-examination rounds
    last_ratings = {}
    labels = {}
    for rnd in range(2, rounds + 1):
        speaking = [sid for sid, st in state.items() if st.get("ballot") and st.get("status") in ("ok", "no_evidence")]
        if len(speaking) < 2:
            log(run_dir, "r%d skipped: fewer than 2 positions to cross-examine" % rnd)
            break
        rng = random.Random(args.seed if args.seed is not None else time.time())
        rng.shuffle(speaking)
        labels = {sid: "M%d" % (i + 1) for i, sid in enumerate(speaking)}
        positions = [(labels[sid], state[sid]["ballot"]) for sid in speaking]
        rated_vote = {sid: state[sid]["ballot"]["vote"] for sid in speaking}
        prompt = prompt_cross(brief, options, workspace, positions, rnd, rounds)
        if secret_scan(dossier(positions)):
            log(run_dir, "r%d: redacted secret-looking strings that seats quoted, before sharing them" % rnd)
            prompt = prompt_cross(brief, options, workspace, positions, rnd, rounds, redact_fn=redact)
        active = [s for s in seats if state[s["id"]].get("status") != "unattended"]
        results = {}
        with cf.ThreadPoolExecutor(max_workers=max(1, len(active))) as ex:
            futs = {ex.submit(sit, s, cfg, prompt, run_dir / ("r%d" % rnd), seat_cwd(s), timeout, option_ids,
                              run_dir, rnd, state[s["id"]]["level"]): s for s in active}
            for f in cf.as_completed(futs):
                results[futs[f]["id"]] = f.result()
        # written only after the round, so no seat could read it while voting
        (run_dir / ("r%d_labels.json" % rnd)).write_text(encoding="utf-8", data=json.dumps(labels, indent=2))
        last_ratings = {}
        for sid, res in results.items():
            st = state[sid]
            st["history"].append(slim(res))
            if res["status"] == "ok" or (res["status"] == "no_evidence" and st.get("status") != "ok"):
                st["status"], st["ballot"] = res["status"], res["ballot"]
                st["model"], st["level"] = res.get("model", st.get("model")), res.get("level", st["level"])
                last_ratings[sid] = res["ballot"].get("ratings", {})
            else:
                st["carried"] = "r%d %s; kept previous ballot" % (rnd, res["status"])

    # peer evidence ratings from the last cross-exam round, self-ratings ignored
    if last_ratings:
        by_label = {v: k for k, v in labels.items()}
        for sid in state:
            state[sid]["ratings_received"] = []
        for rater, ratings in last_ratings.items():
            for lab, val in ratings.items():
                target = by_label.get(lab)
                if target and target != rater:
                    state[target]["ratings_received"].append(val)
        for sid, st in state.items():
            # ratings judged the position shown in the dossier; a seat that then switched sides starts neutral
            if st["ratings_received"] and st.get("ballot") and st["ballot"].get("vote") != rated_vote.get(sid):
                st["ratings_received"] = []
                st["ratings_note"] = "switched vote after being rated; weight neutral"

    if fp_before is not None and workspace_fingerprint(workspace) != fp_before:
        meta["workspace_changed"] = True
        (run_dir / "meta.json").write_text(encoding="utf-8", data=json.dumps(meta, indent=2, ensure_ascii=False))
        log(run_dir, "WARNING: the workspace changed during the council (git status/diff differ); a seat may have written files")
    finish(run_dir, meta, state, options, cfg)
    return 3 if meta.get("workspace_changed") else 0


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build", "target"}


def git_toplevel(ws):
    try:
        r = subprocess.run(["git", "-C", str(ws), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def workspace_fingerprint(ws):
    """Detect a seat that broke the read-only rule. Git checkout (also from a subdirectory): HEAD + status +
    tracked diff + hashes of untracked files. Otherwise: path/size/mtime of every file (caches skipped)."""
    if not ws:
        return None
    top = git_toplevel(ws)
    if top:
        def git(*a):
            return subprocess.run(["git", "-C", str(top)] + list(a), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120).stdout
        try:
            untracked = [l for l in git("ls-files", "-o", "--exclude-standard", "-z").split("\0") if l]
            hashes = subprocess.run(["git", "-C", str(top), "hash-object", "--stdin-paths"], input="\n".join(untracked),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=120).stdout if untracked else ""
            return "\0".join([git("rev-parse", "HEAD"), git("status", "--porcelain", "-uall"), git("diff", "HEAD"), hashes])
        except (subprocess.SubprocessError, OSError):
            return None
    rows = []
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.lstat(fp)
            except OSError:
                continue
            rows.append("%s %d %d" % (os.path.relpath(fp, ws), st.st_size, st.st_mtime_ns))
            if len(rows) > 50000:
                return None
    return "\n".join(sorted(rows))


def snapshot_workspace(ws, dest, limit=300 * 1024 * 1024):
    """Copy the workspace's tracked + untracked (not ignored) files to dest, for seats whose CLI cannot be
    made read-only. Returns dest, or None if ws is not a git checkout or is larger than limit."""
    top = git_toplevel(ws)
    if not top:
        return None
    out = subprocess.run(["git", "-C", str(ws), "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=120).stdout
    files = [f for f in out.split("\0") if f]
    total = 0
    for f in files:
        src = ws / f
        if not src.is_file() or src.is_symlink():
            continue
        total += src.stat().st_size
        if total > limit:
            return None
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / f)
    return dest


def slim(res):
    return {k: res.get(k) for k in ("status", "model", "level", "detail", "secs", "ballot", "attempts")}


def finish(run_dir, meta, state, options, cfg):
    t = tally(state, options, meta.get("decision_rule", "weighted"))
    quorum = meta.get("quorum", 2)
    if t["valid_votes"] < quorum:
        t["verdict"], t["no_quorum"] = None, True
    result = {"meta": {k: meta[k] for k in ("title", "options", "rounds", "mode", "workspace", "private", "decision_rule", "quorum", "started")},
              "workspace_changed": bool(meta.get("workspace_changed")),
              "finished": dt.datetime.now().isoformat(timespec="seconds"),
              "tally": t,
              "seats": {sid: {k: st.get(k) for k in ("status", "model", "level", "weight", "tiebreak", "ballot", "history",
                                                      "carried", "ratings_received", "ratings_note")}
                        for sid, st in state.items()},
              "skipped": meta.get("skipped", [])}
    (run_dir / "result.json").write_text(encoding="utf-8", data=json.dumps(result, indent=2, ensure_ascii=False))
    (run_dir / "decision.md").write_text(encoding="utf-8", data=render(result))
    log(run_dir, "done: verdict %s" % (t["verdict"] or ("NO QUORUM" if t.get("no_quorum") else "TIE")))
    print((run_dir / "decision.md").read_text(encoding="utf-8"))


def render(result):
    t, meta, seats = result["tally"], result["meta"], result["seats"]
    labels = dict((o, l) for o, l in meta["options"])
    out = ["# Roundtable: %s" % meta["title"], ""]
    if result.get("workspace_changed"):
        out += ["> **WARNING:** files in the workspace changed during the council. A seat may have broken the "
                "read-only rule; check `git status` before trusting or keeping anything.", ""]
    if t.get("no_quorum"):
        out.append("**Verdict: NO QUORUM** (%d valid ballot(s), need %d). Do not treat this as a decision." % (t["valid_votes"], meta["quorum"]))
    elif t["verdict"] is None:
        out.append("**Verdict: TIE, escalate to the user.** %s" % t["tiebreak"])
    else:
        v = t["verdict"]
        out.append("**Verdict: %s: %s**  (weighted %.2f of %.2f, %d of %d valid votes)"
                   % (v, labels[v], t["score"][v], t["total_weight"], t["count"][v], t["valid_votes"]))
        if t["tiebreak"]:
            out += ["", "Tie-break: %s." % t["tiebreak"]]
    out += ["", "Rule: %s vote; weight = seat weight x (0.5 + 0.5 x mean peer evidence rating 0-2); "
                "ballots without FACT/INFERENCE evidence do not count; ties go to the Fable seat." % meta["decision_rule"], ""]
    out += ["## Tally", "", "| Option | Weighted | Votes | Seats |", "|---|---|---|---|"]
    for o, l in meta["options"]:
        out.append("| %s: %s | %.2f | %d | %s |" % (o, l, t["score"][o], t["count"][o], ", ".join(t["voters"][o]) or "-"))
    out += ["", "## Seats", "", "| Seat | Model | Status | Vote | Conf. | Peer evidence | Weight | Path |", "|---|---|---|---|---|---|---|---|"]
    rows = {r["seat"]: r for r in t["rows"]}
    for sid, st in seats.items():
        b = st.get("ballot") or {}
        hist = " / ".join("r%d %s" % (i + 1, h["status"]) for i, h in enumerate(st.get("history") or []))
        model = st.get("model") or "-"
        if st.get("level"):
            model += " (fallback)"
        out.append("| %s | %s | %s | %s | %s | %s | %.2f | %s |" % (
            sid, model, "UNATTENDED" if st.get("status") == "unattended" else st.get("status"),
            b.get("vote") or "-", "%.2f" % b["confidence"] if b else "-",
            rows[sid]["peer_score"] if rows[sid]["peer_score"] is not None else "-", rows[sid]["weight"], hist))
    unatt = [(sid, st) for sid, st in seats.items() if st.get("status") == "unattended"]
    if unatt or result.get("skipped"):
        out += ["", "## Unattended", ""]
        for sid, st in unatt:
            out.append("- **%s**: %s" % (sid, (st.get("history") or [{}])[0].get("detail") or "no model answered"))
        for s in result.get("skipped", []):
            out.append("- **%s**: %s" % (s["id"], s["reason"]))
    changed = []
    for sid, st in seats.items():
        votes = [(h.get("ballot") or {}).get("vote") for h in st.get("history") or [] if h.get("status") == "ok"]
        if len(votes) >= 2 and votes[0] != votes[-1]:
            dec = "; ".join((st.get("ballot") or {}).get("decisive_evidence") or []) or "no reason given"
            changed.append("- **%s**: %s -> %s because: %s" % (sid, votes[0], votes[-1], dec[:400]))
    if changed:
        out += ["", "## Changed votes", ""] + changed
    v = t["verdict"]
    if v:
        out += ["", "## Evidence for %s" % v, ""]
        for sid in t["voters"][v]:
            b = seats[sid]["ballot"]
            out.append("- **%s**: %s" % (sid, b["summary"]))
            for e in b["evidence"][:5]:
                out.append("  - [%s] %s (%s)" % (e["type"], e["claim"], e["source"] or "no source"))
    dissent = [(sid, st) for sid, st in seats.items() if v and st.get("status") == "ok" and st["ballot"]["vote"] != v]
    if dissent:
        out += ["", "## Dissent", ""]
        for sid, st in dissent:
            b = st["ballot"]
            out.append("- **%s** voted %s: %s" % (sid, b["vote"], b["summary"]))
            for e in b["evidence"][:3]:
                out.append("  - [%s] %s (%s)" % (e["type"], e["claim"], e["source"] or "no source"))
    risks = [(sid, x) for sid, st in seats.items() if st.get("ballot") for x in (st["ballot"].get("risks") or []) + (st["ballot"].get("conditions") or [])]
    if risks:
        out += ["", "## Risks and conditions raised", ""] + ["- (%s) %s" % (sid, x) for sid, x in risks[:20]]
    out += ["", "Run finished %s. Full transcripts: r1/, r2/ ... next to this file." % result["finished"], ""]
    return "\n".join(out)


def cmd_tally(args):
    run_dir = Path(args.run)
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    meta["options"] = [tuple(o) for o in meta["options"]]
    cfg = load_config(args.config)
    finish(run_dir, meta, res["seats"], meta["options"], cfg)
    return 0


def cmd_status(args):
    runs = [p for p in RUNS_DIR.glob("*") if (p / "meta.json").exists()]
    run_dir = Path(args.run) if args.run else max(runs, key=lambda p: p.stat().st_mtime, default=None)
    if not run_dir or not run_dir.exists():
        raise SystemExit("no run found in %s" % RUNS_DIR)
    print(run_dir)
    prog = run_dir / "progress.log"
    if prog.exists():
        print(prog.read_text(encoding="utf-8").rstrip())
    if (run_dir / "decision.md").exists():
        print("DONE")
        return 0
    pid = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")).get("pid")
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except PermissionError:
            alive = True
        except OSError:
            alive = False
    if alive:
        print("RUNNING" if prog.exists() else "STARTING")
    else:
        print("FAILED (runner exited without decision.md; see rt log / progress.log)")
    return 0 if alive else 1


def cmd_doctor(args):
    cfg = load_config(args.config)
    seats, skipped = resolve_seats(cfg, (args.seats or "full").split(","), private=args.private)
    probe_dir = RUNS_DIR / ("doctor-%s" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    rows = []

    def check(seat, i, model):
        adapter = cfg["adapters"][seat["adapter"]]
        if not shutil.which(adapter["bin"]):
            return seat["id"], i, model, "missing", "%s not on PATH" % adapter["bin"]
        if not args.probe:
            return seat["id"], i, model, "found", ""
        d = probe_dir / seat["id"] / str(i)
        sandbox = probe_dir / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        res = call_cli(adapter, model, "Connectivity check for a decision tool. Question: is 2 + 2 equal to 4? "
                       "Options: A = yes, B = no. End your answer with a JSON object like "
                       '{"vote": "A", "evidence": [{"type": "FACT", "claim": "2 + 2 = 4", "source": "arithmetic"}]}',
                       d, sandbox, args.timeout or 180, seat["id"])
        res = classify(res, ["A", "B"])
        if res["status"] == "unavailable" and "deprecated" in res.get("detail", "").lower():
            remember_dead(model)
        return seat["id"], i, model, res["status"], res.get("detail", "")

    jobs = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for s in seats:
            if s.get("unresolved"):
                rows.append((s["id"], 0, "-", "unresolved", s["unresolved"]))
                continue
            for i, m in enumerate(s["models"]):
                jobs.append(ex.submit(check, s, i, m))
        for j in jobs:
            rows.append(j.result())
    rows.sort(key=lambda r: ([s["id"] for s in seats].index(r[0]), r[1]))
    print("%-10s %-9s %-30s %-12s %s" % ("seat", "level", "model", "status", "detail"))
    for sid, i, m, st, det in rows:
        print("%-10s %-9s %-30s %-12s %s" % (sid, "primary" if i == 0 else "fallback", m, st, det[:80]))
    for s in seats:
        if s.get("fallback_dropped"):
            print("note: %s fallback %s dropped (it is another seat's primary)" % (s["id"], s["fallback_dropped"]))
        if s.get("homogeneous"):
            print("note: %s is a same-vendor alt seat; votes are less independent" % s["id"])
    for s in skipped:
        print("skipped: %s (%s)" % (s["id"], s["reason"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="roundtable", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="extra config merged over the defaults (default ~/.config/roundtable/seats.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="convene the council")
    r.add_argument("--brief", required=True, help="markdown brief file ('-' = stdin); may hold a '## Options' section")
    r.add_argument("--option", action="append", help="option as ID='text' (repeatable); overrides the brief's Options")
    r.add_argument("--mode", choices=["decide", "review"], default="decide", help="review = APPROVE/CHANGES/REJECT gate")
    r.add_argument("--seats", help="comma list of seat ids or presets (default: full)")
    r.add_argument("--rounds", type=int, help="1 = blind vote only, 2 = + one cross-exam (default), 3 = two cross-exams")
    r.add_argument("--workspace", help="directory seats may read (read-only); default: none, seats run in empty sandboxes")
    r.add_argument("--private", action="store_true", help="drop seats whose provider may train on prompts (free opencode models)")
    r.add_argument("--allow-sensitive", action="store_true", help="skip the secret scan block (false positives only)")
    r.add_argument("--timeout", type=int, help="seconds per seat per round (default 900)")
    r.add_argument("--title")
    r.add_argument("--out", help="run directory (default ~/.roundtable/runs/<time>-<slug>)")
    r.add_argument("--seed", type=int, help="seed for the anonymous label shuffle")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("doctor", help="list seats and (with --probe) ping every model")
    d.add_argument("--seats")
    d.add_argument("--probe", action="store_true")
    d.add_argument("--private", action="store_true")
    d.add_argument("--timeout", type=int)
    d.set_defaults(func=cmd_doctor)

    s = sub.add_parser("status", help="progress of a run (default: latest)")
    s.add_argument("run", nargs="?")
    s.set_defaults(func=cmd_status)

    t = sub.add_parser("tally", help="recompute decision.md from a finished run")
    t.add_argument("run")
    t.set_defaults(func=cmd_tally)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
