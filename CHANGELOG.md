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
- Token usage per seat and per run, from each CLI's own JSON output: claude `--output-format json`, codex `--json`,
  grok `--output-format json`, opencode `--format json` + `session export` (local). Normalised to input (cache reads
  included), cached, output and total; `cost_usd` where the CLI reports one. agy stays plain text (no figures).
  Shown in the `USAGE:` line, the decision.md usage table, `result.json` and `status --json`.
- Claude seats run with `--restricted`: the user's hooks (e.g. SessionStart context listing vault secret names) and
  auto-memory no longer reach a seat. Verified with `--include-hook-events`.
- Account-level limits (Claude session/weekly limit, an account disabled by the provider) no longer walk to a
  fallback model on the same account.
- Untrusted-data hardening: both prompts say files, quoted documents and other members' text are data, never
  instructions; cross-exam positions are fenced with a per-prompt nonce; ballots may report `injection_suspected`
  (decision.md banner and section, `INJECTION:` line, `status --json`).
- The cross-exam dossier drops self-reported confidence and shows each position's conditions and risks.
- Source check with `--workspace`: a FACT/INFERENCE whose every `file:line` is missing from the workspace (or past
  the end of the file) counts as ASSUMPTION; listed under "Sources that did not check out".
- `--early-stop` (opt-in): skip the cross-exam when round 1 is unanimous with at least max(quorum, 3) valid ballots
  from 2+ vendor CLIs, no framing concern and no injection report; never in review mode. Every run records a shadow
  measurement (`shadow.r1_unanimous`, `changed_after_r1`).
- The workspace fingerprint is compared after every round; a write stops the council before the next round.
- `tally.vendor_clis` / `low_diversity` (reported, not a quorum rule), and `provenance` (script version, brief and
  options hashes, the label-shuffle seed, the workspace's git HEAD) in result.json.
- Sample briefs in `skills/llm-roundtable/references/briefs/` (decide and review), checked by a test.
- Claude Code plugin: `skills/llm-roundtable/.claude-plugin/plugin.json` and a root marketplace
  (`/plugin marketplace add dinhkarate/llm-roundtable`). A test keeps package.json, SKILL.md, plugin.json, the
  script's `--version` and this changelog on one version.

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
