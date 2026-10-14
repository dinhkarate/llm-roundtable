# Changelog

## 0.2.0 (unreleased)

- Versioned result contract: `result.json` carries `schema_version: 2`; `status --json` prints one object with
  `state` (STARTING/RUNNING/DONE/TAINTED/FAILED), `verdict`, `decided_by`, `actionable`, `council_verdict`, margin,
  framing, conditions, kill criteria, unresolved questions, unattended seats and usage. Plain `status` still ends with
  `DONE` then `VERDICT: ...`; new lines (`USAGE:`, `MARGIN:`, `FRAMING:`) come before them.
- Usage summary in `decision.md` and `result.json` (`usage`): CLI calls per seat, nudges, fallback calls, unattended,
  skipped and carried seats, wall time per round and in total. The call before a nudge was lost from `result.json`;
  every attempt now records `round`, `kind` (primary/fallback/nudge) and `level`. Round timings persist in meta.json,
  so `tally` reproduces them.
- `run --dry-run`: same validation as `run`, then the plan as JSON (seats, fallbacks, missing CLIs, `--private` skips,
  quorum, call and wall-time bounds, unparsed `## Options` lines, argv prompt size). No run directory, no model call.
- Unknown `--seats` now fails before `--detach`, on the caller's stderr.
- Kill criteria and `UNKNOWN` evidence: optional `kill_criteria` on ballots, listed for the winning side in
  `decision.md`; `UNKNOWN` items are open questions, never count as evidence, are kept out of rated and rendered
  evidence and are listed under "Unresolved questions".
- Framing check in round 1 (`restatement`, `missing_option`): an advisory `framing_concern` when at least
  max(2, ceil(n/2)) valid seats name a missing option. The vote is unchanged.
- `--min-margin X` (or `min_margin` in seats.json), off by default: a winner whose share of the valid weight is below X
  falls back to `--default` like a TIE; `tally.council_verdict` keeps the council's pick. The share is always recorded.
- `--deadline SECONDS`: a whole-run budget; calls are cut at it, no new call starts after it and the ballots so far are
  tallied.
- `--timeout` help now says "per CLI call".

## 0.1.1 (2026-10-14)

- `run --detach`: prints the run directory and continues in its own session. Codex kills a tool call's
  processes when the call returns, so `nohup ... &` councils died there.
- `status` prints the `VERDICT:` line when a run is DONE (or `VERDICT: NONE (workspace_changed)` when TAINTED).
- Docs: tested skill discovery from Claude Code, Codex, Grok CLI, OpenCode and Antigravity (references/hosts.md).

## 0.1.0 (2026-10-14)

First public release.

- Six-seat council across five vendors: Claude Fable, Claude Opus, GPT (Codex CLI), Grok, Gemini (Antigravity), newest free OpenCode model.
- Blind round + anonymous cross-exam, evidence-rated weighted vote, Fable tie-break, safe `--default`.
- One-level fallback per model family, then UNATTENDED.
- Review mode for plans, diffs and PRs (`APPROVE / CHANGES / REJECT`).
- Read-only, sandboxed seats; publishing tools removed; credentials stripped; workspace tamper check.
- Survives host sleep and stop signals; `status` for detached runs.
- `npx llm-roundtable` wrapper.
