---
name: llm-roundtable
description: Decide in the user's place when the user is not there. Convenes a council of AI models from different vendors (Fable, Opus, GPT via Codex, Grok, Gemini via Antigravity, newest free OpenCode model) that gather evidence, cross-examine each other anonymously and cast weighted, evidence-backed votes; the highest weighted option wins, ties go to the Fable seat, and an undecided council falls back to a safe default. Use automatically in unattended or autonomous runs (Orca workers, orca-pod bots, long /loop or /goal sessions, overnight work) whenever you would otherwise stop to ask the user to choose, approve or review something (design choice, plan, PR/diff, migration, risky change). Also use when the user says /llm-roundtable or /roundtable, "hội bàn tròn", "hội đồng", "council", "cho mấy con AI bàn/phản biện/duyệt". Works from Claude Code, Codex, Grok CLI, Antigravity, OpenCode or pi — any agent with a shell.
version: 0.1.0
tags: [decision, review, multi-model, debate, voting, council]
---

# llm-roundtable

The council stands in for the user while the user is away, so work does not stall on a question.
You are the **moderator**, never a voter: turn the question into a brief, run `scripts/roundtable.py`,
then act on the verdict. Each member is a separate CLI process (fresh context, read-only), even if it
is the same product you are running in.

## When

- **User away** (autonomous run, Orca worker, orca-pod bot, /loop, /goal, overnight): every time you
  would stop and ask the user to pick, approve or review, convene the council instead and keep going.
- **User present**: run it when they ask for it; otherwise just ask them, they are the better judge.
- Skip it for questions with one checkable answer (run the check instead), for anything the user or
  the task already decided, and for trivial reversible choices (just pick one and say so).

## 1. Write the brief

Create a markdown file (e.g. `$TMPDIR/roundtable-brief.md`):

```markdown
# <the decision, one line>

<context: goal, constraints, what has been tried, what is at stake, deadline>
<facts members can verify: file paths (with --workspace), URLs, numbers, error text>

## Options
- A: <option, concrete enough to act on>
- B: <...>
- C: <...>   (2-5 options; include "do nothing / defer" when it is a real choice)
```

Always pass `--default <option>`: the safest, most reversible option (often "defer" or "smallest
change"). It is what happens when the council cannot decide; nobody is there to break a deadlock.

- Members cannot see this conversation. The brief must stand alone.
- Neutral wording: do not reveal which option you or the user prefer.
- **Privacy gate.** The brief goes to Anthropic, OpenAI, xAI, Google and an OpenCode free provider
  (free models may train on prompts). Never include secrets (the script blocks obvious ones),
  customer data or employer-confidential material. For company work (e.g. EONSR) use `--private`
  (drops seats that may train on data) and anonymize; if it still cannot leave the machine,
  do not run a council.
- Approval of a plan / diff / PR: use `--mode review` (options APPROVE / CHANGES / REJECT) and
  either paste the artifact into the brief or pass `--workspace <repo>` so members read it.

## 2. Run

```bash
S=<this skill dir>/scripts/roundtable.py
python3 $S doctor                 # who can sit (CLI on PATH); add --probe to ping every model
python3 $S run --brief brief.md   # full council, 2 rounds
```

A council takes 5-20 minutes, longer than most tool timeouts (Claude Code stops even background
commands at their timeout). On every host, start it detached and poll:

```bash
nohup python3 $S run --brief brief.md > "${TMPDIR:-/tmp}/rt.log" 2>&1 &
sleep 2; RUN=$(head -1 "${TMPDIR:-/tmp}/rt.log")   # first line = run directory
python3 $S status "$RUN"   # every 1-2 min: STARTING / RUNNING / DONE / TAINTED / FAILED
```

On a laptop keep the lid open or the machine on power: a sleeping host stalls every seat
(the script holds `caffeinate` on macOS, which cannot stop lid-close sleep on battery).

Always pass `$RUN`: a bare `status` shows the newest run, which may be someone else's. In Claude Code
you may wait with a background `until python3 $S status "$RUN" | grep -qE '^(DONE|TAINTED|FAILED)'; do sleep 30; done`
(re-arm it if it times out) instead of polling by hand.

TAINTED (exit code 3 from `run`, 4 from `status`, `VERDICT: NONE (workspace_changed)`) means files in
`--workspace` changed while the council ran. Nothing from that run is actionable: run `git status`
there, restore anything a seat touched, and treat the question as undecided.

Useful flags: `--seats duo` (Fable + Opus only), `--seats fable,codex,grok`, `--rounds 1`
(blind vote, cheapest) or `3`, `--workspace .` (members may read the repo, read-only),
`--private`, `--timeout 600`, `--option A='...'` instead of an Options section,
`--default B` (review mode defaults to CHANGES).
Presets: `full`, `duo`, `solo-codex`, `solo-grok`, `solo-agy` (see references/hosts.md).

## 3. Act on the verdict

The last line of the output is `VERDICT: <option|NONE> (council|tiebreak|default|none|workspace_changed)`; details are in
`decision.md` in the run directory.

- **council / tiebreak / default**: carry out that option, including its "conditions". Do not overrule
  it, re-run until you like the answer, or swap in your own preference.
- **NONE** (no `--default` and no decision, or a TAINTED run): take the most reversible path, usually
  leaving the change undone, and move on to other work.
- Leave a trail where the user will look later (PR description, issue comment, commit message, or your
  final report): the question, the verdict and how it was reached, the 2-3 strongest pieces of evidence,
  the strongest dissent, and unattended seats (e.g. "gemini UNATTENDED: 3.8 quota, 3.7 not offered").
  Link or paste the run directory path.
- The council replaces the user's *judgment* inside the work the user already handed you, not their
  *authority*. It picks between options; it does not widen what you may do. Actions that need the
  user's standing permission (push to shared branches, merge, deploy, publish, message people) still
  need it; the council can only choose among actions you were already allowed to take. It never
  authorizes leaking secrets, deleting data or backups, or spending money.
- If the user is present and asks, report the same items instead of acting, and give your own view
  separately, labelled as yours.

## Rules the script enforces

- Seats (default): fable `claude-fable-5-1`, opus `claude-opus-5-5`, codex `gpt-6.1-sol`,
  grok `grok-4.7`, gemini `gemini-3.8-flash-high` (Antigravity), opencode = newest free OpenCode
  model whose family differs from the others.
- Fallback: one level down in the same family only (fable 5, opus 5, gpt-6-sol, grok-4.6,
  gemini 3.7 flash, next-newest free OpenCode model) on quota / unavailable / error / timeout.
  Still failing, or CLI missing: the seat is **UNATTENDED**.
- Round 1 blind; round 2+ shows every position anonymized (M1, M2...) and asks for evidence ratings
  (0-2), rebuttals and a fresh vote. Ballots without sourced FACT/INFERENCE evidence do not count.
- Seats are read-only and cannot publish: allowlisted read tools only (claude), kernel sandboxes
  (codex, grok), agy in its own sandbox on a snapshot copy of the workspace, MCP/app tools removed,
  unrelated credentials stripped from their environment. Only a seat's final answer can carry its ballot.
- Weight = seat weight x (0.5 + 0.5 x mean peer rating, self-ratings ignored). Highest weighted
  score wins; a tie goes to the option the Fable seat voted for, else TIE. Fewer than 2 valid ballots:
  NO QUORUM. TIE or NO QUORUM falls back to `--default`.
- A seat refuses to convene a council itself (`ROUNDTABLE_SEAT` guard).

Details: `references/protocol.md` (rounds, prompts, maths), `references/hosts.md` (per-host setup,
Orca, single-tool setups, config overrides).
