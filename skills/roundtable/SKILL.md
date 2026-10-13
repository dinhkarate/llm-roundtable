---
name: roundtable
description: Convene a council of AI models from different vendors (Fable, Opus, GPT via Codex, Grok, Gemini via Antigravity, newest free OpenCode model) that each gather evidence, cross-examine each other anonymously and cast weighted, evidence-backed votes; the option with the highest weighted score wins and ties go to the Fable seat. Use when the user says /roundtable, "hội bàn tròn", "hội đồng", "council", "cho mấy con AI bàn/phản biện/duyệt", asks for a multi-model second opinion, or wants something approved (plan, PR, architecture, migration, risky or irreversible change). Also offer it (do not start it unasked) before a high-stakes, hard-to-reverse decision. Works from Claude Code, Codex, Grok CLI, Antigravity, OpenCode or pi — any agent with a shell.
version: 0.1.0
tags: [decision, review, multi-model, debate, voting, council]
---

# roundtable

You are the **moderator**, never a voter. You turn the question into a brief, run
`scripts/roundtable.py`, and report the verdict faithfully. Each member is a separate CLI process
(fresh context, read-only), even if it is the same product you are running in.

## When

- Run it when the user asks (any trigger above) or when an approval gate the user set up calls for it.
- Otherwise only *propose* it: a full council costs ~12 model calls and 5-20 minutes.
- Skip it for questions with one checkable answer (run the check instead) and for anything
  the user already decided.

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
nohup python3 $S run --brief brief.md > "$TMPDIR/rt.log" 2>&1 &
sleep 2; RUN=$(head -1 "$TMPDIR/rt.log")   # first line = run directory
python3 $S status "$RUN"   # every 1-2 min: STARTING / RUNNING / DONE / FAILED (runner died: read rt.log)
```

On a laptop keep the lid open or the machine on power: a sleeping host stalls every seat
(the script holds `caffeinate` on macOS, which cannot stop lid-close sleep on battery).

Always pass `$RUN`: a bare `status` shows the newest run, which may be someone else's. In Claude Code
you may wait with a background `until python3 $S status "$RUN" | grep -qE '^(DONE|FAILED)'; do sleep 30; done`
(re-arm it if it times out) instead of polling by hand.

Exit code 3 / a WARNING banner in decision.md means files in `--workspace` changed while the council
ran. Run `git status` there and tell the user before trusting anything.

Useful flags: `--seats duo` (Fable + Opus only), `--seats fable,codex,grok`, `--rounds 1`
(blind vote, cheapest) or `3`, `--workspace .` (members may read the repo, read-only),
`--private`, `--timeout 600`, `--option A='...'` instead of an Options section.
Presets: `full`, `duo`, `solo-codex`, `solo-grok`, `solo-agy` (see references/hosts.md).

## 3. Report

Read `decision.md` in the run directory (path printed first; also `~/.roundtable/runs/`). Tell the user:

1. The verdict line as written (option, weighted score, votes). If it says **TIE** or
   **NO QUORUM**, say so plainly: there is no decision; give the split and ask the user.
2. The 2-4 strongest evidence items for the winner, and the strongest dissent.
3. Unattended seats and fallbacks (e.g. "gemini UNATTENDED: 3.8 quota, 3.7 not available").
4. Conditions and risks members attached.

Never overrule or "correct" the vote, never re-run until you like the answer, and do not act on
an outward-facing or irreversible step just because the council approved it: the user's own
confirmation rules still apply. If the user asks for your view, give it separately and label it.

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
  (codex, grok), a snapshot copy of the workspace (agy), MCP/app tools removed.
- Weight = seat weight x (0.5 + 0.5 x mean peer rating, self-ratings ignored). Highest weighted
  score wins; a tie goes to the option the Fable seat voted for, else TIE. Fewer than 2 valid ballots: NO QUORUM.
- A seat refuses to convene a council itself (`ROUNDTABLE_SEAT` guard).

Details: `references/protocol.md` (rounds, prompts, maths), `references/hosts.md` (per-host setup,
Orca, single-tool setups, config overrides).
