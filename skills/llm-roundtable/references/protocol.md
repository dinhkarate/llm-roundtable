# Protocol

## Roles

- **Moderator**: the agent the user is talking to. Writes the brief, runs the script, reports.
  Does not vote, does not edit ballots.
- **Seats**: one CLI process per member per round, fresh session each time (`--ephemeral`,
  `-p`), read-only and without publishing tools:

  | CLI | Read-only by | Outward tools removed |
  |---|---|---|
  | claude | `--permission-mode dontAsk` + allowlist: Read/Grep/Glob/WebSearch/WebFetch, `ls`, `wc`, `git status`, `git ls-files` (no code execution; no `rg`/`git diff`, whose `--pre`/`--output` run or write) | `--strict-mcp-config` (no MCP servers), `--tools` without Agent |
  | codex | `-s read-only` sandbox (kernel) | `--disable apps computer_use browser_use` |
  | grok | `--sandbox read-only` (kernel; temp dirs stay writable) | no MCP configured |
  | agy | `--sandbox` without `--dangerously-skip-permissions` (that flag can lift the sandbox, agy issue #36; headless then denies prompt-gated tools like read_url) and `"isolate": true`: with `--workspace` it works in a snapshot copy of the checkout's tracked + untracked files | no MCP configured |
  | opencode | `--agent plan` and `PWD` set to its sandbox; **not** a sandbox: its background service can still run shell commands anywhere (`--private` drops this seat) | no MCP configured |

  Plan modes are avoided on claude and grok: they inject "write a plan, exit plan mode" instructions
  and end headless runs before the ballot. Each call gets `ROUNDTABLE_SEAT=<id>` so a seat that loads
  this skill cannot start a nested council. With `--workspace`, the script fingerprints it before and
  after (git checkout, also from a subdirectory: HEAD, status, diff, untracked file hashes; otherwise
  path/size/mtime of every file); any change gives a WARNING banner and exit code 3. Secret-looking
  strings that seats quote are redacted before the cross-exam dossier goes to the other vendors.
- **Isolation of the anonymity**: seat working directories are fresh temp dirs outside the run
  directory, and `rN_labels.json` is written only after round N has finished.
- **Cleanup**: SIGINT/SIGTERM/exit kill every running seat's process group.
- **Provenance**: a ballot is read only from the seat's final answer (stdout, or codex's last message), never
  from stderr or echoed tool output. Seats get the parent environment minus credentials their CLI does not
  need. Prompts and transcripts live in a temp dir during a round and are copied into the run dir after it.
- **Tainted runs**: a changed workspace makes the run non-actionable: `VERDICT: NONE (workspace_changed)`,
  `run` exits 3, `status` prints TAINTED and exits 4.

## Rounds

| Round | Members see | Members return |
|---|---|---|
| 1 (blind) | brief + options | vote, confidence, summary, evidence[], risks, conditions, kill_criteria[] (optional), restatement, missing_option |
| 2..3 (cross-exam) | brief + every previous position as M1..Mn, shuffled, own one unmarked; open questions on a line of their own | vote, confidence, summary, evidence[], risks, conditions, kill_criteria[] + ratings{Mi: 0-2}, rebuttals[], decisive_evidence[] |

Default 2 rounds. Each cross-exam round is a new session, so a member does not remember its own
earlier answer; the anonymity is real, not a request to "please ignore names".

Evidence types: `FACT` (verified, with a source), `INFERENCE` (reasoned from cited facts),
`ASSUMPTION` (unverified), `UNKNOWN` (an open question that matters and that the seat could not answer).
FACT or INFERENCE items without a source are downgraded to ASSUMPTION.
A ballot needs at least one FACT or INFERENCE item to count
(`no_evidence` otherwise; a ballot with only UNKNOWN items is `no_evidence`). A vote that is not one of
the option ids is `invalid`. UNKNOWN items are kept out of the rated and rendered evidence: the dossier
lists them as "open questions (UNKNOWN, not evidence)" and the cross-exam prompt says not to treat them as
evidence when rating; decision.md lists them under "Unresolved questions".

**Kill criteria** (optional, any round): observable signals that would show later that the choice was
wrong, phrased "If <X> is observed, ...". decision.md lists those of the seats whose final valid ballot
voted for the verdict ("Kill criteria for V", seat-attributed, at most 20). When the verdict is the
`--default`, the heading says it is the safe default and not a council choice. Hosts report and watch
them; the script never acts on them.

**Framing check** (round 1 only): `restatement` (the decision in one sentence; audit only, never
compared) and `missing_option` (empty, or one concrete action the options left out; not a mix of the
listed options). Read from the round-1 history after the last round, so round 2 cannot erase it.
`framing_concern` is true when the seats with a valid round-1 ballot that named a missing option number
at least `max(2, ceil(n_valid / 2))` (duo: both seats; six: three). It is advisory: the tally, the verdict
and the `VERDICT:` line are unchanged; decision.md shows a banner and a "Framing check" section, and
`status` prints `FRAMING: concern (k/n ...)` before `DONE`.

## Seat lifecycle

```
primary model --(quota | unavailable | error | timeout)--> fallback model (same family, one level down)
     |                                                          |
     ok / no_evidence / invalid: stop                           fails too -> UNATTENDED
CLI missing on PATH -> UNATTENDED immediately
```

- Status is taken from the process: a parsed ballot wins; otherwise stderr/stdout is matched against
  quota patterns (rate limit, 429, usage limit, quota, credits...) and unavailable patterns
  (unknown model, not supported, deprecated, may not exist...).
- A seat that fell back in round 1 starts later rounds on the fallback model.
- If a seat fails in a later round, its previous ballot is carried forward and marked.
- A fallback that equals another seat's primary is dropped (two seats must not be the same voice).
- OpenCode `auto:opencode-free`: `opencode models` filtered to `opencode/*free` (or zero cost on
  models.dev), excluding families that already sit (claude, gpt, grok, gemini...) and models marked
  deprecated by models.dev or seen failing as deprecated (`~/.roundtable/dead-models.json`), newest
  release date first. `count: N` seats N distinct models; seat i falls back to candidate i+N.

## Tally

```
peer(seat)   = mean of the 0-2 ratings other members with a valid ballot gave it in the last cross-exam
               (1.0 if none, and 1.0 if the seat switched vote after the position they rated)
weight(seat) = seat.weight x (0.5 + 0.5 x peer)          -> 0.5x .. 1.5x
score(opt)   = sum of weight over valid ballots for opt
verdict      = argmax score                               (decision_rule "count": argmax votes, score breaks ties)
tie          -> option the tiebreak seat (Fable) voted for; Fable not on a tied option -> TIE
valid ballots < quorum (2) -> NO QUORUM
share        = score(winner) / sum of score over valid ballots   (unrounded; after the tie-break;
               weighted under both decision rules; undecided: the top option's share; no valid weight: null)
--min-margin X (opt-in, also "min_margin" in seats.json): share < X - 1e-9 -> treated like a TIE:
               tally.council_verdict = the council's pick, tally.narrow_margin = true, no second tie-break
TIE / NO QUORUM / narrow margin -> --default (safe option from the brief; review mode: CHANGES), else VERDICT NONE
precedence   : tainted workspace > NO QUORUM > narrow margin > TIE
```

`X` is a number or fraction in (0, 1]. The comparison is inclusive: a uniform 4-2 split of six has share
0.6667, which passes `2/3` and fails `0.67`. A high floor turns the council into "always the default";
peer ratings move weights between 0.5x and 1.5x, so shares near the floor are noisy. The share is always
recorded and printed (`Margin:` in decision.md, `MARGIN:` from `status`), with or without the flag.

A whole-run `--deadline SECONDS` (opt-in) starts with the run: each call's timeout is cut to what is
left, no call (fallback or nudge included) starts after it, a later round is skipped, and the ballots
so far are tallied (carried ballots included). Seat discovery is not interrupted.

Confidence is recorded but not weighted: self-reported confidence is poorly calibrated and easy to
inflate. Peer-rated evidence is the weight because that is what the user asked the council to
argue over.

## Result contract (schema_version 2)

`result.json` and `status --json` carry `schema_version: 2` (v0.1 results have none and read as 1).
The text contract does not change: a foreground `run` ends with
`VERDICT: <option|NONE> (council|tiebreak|default|none|workspace_changed)`, and `status` ends with `DONE`
(or `TAINTED`) and then that line; new lines (`USAGE:`, `MARGIN:`, `FRAMING:`) always come before them.

| result.json | Meaning |
|---|---|
| `tally.verdict`, `tally.decided_by` | what to act on, as in the `VERDICT:` line |
| `tally.council_verdict` | the council's own pick when it is not acted on (tainted run, narrow margin) |
| `tally.share`, `tally.share_of`, `tally.min_margin`, `tally.narrow_margin` | margin, see Tally |
| `tally.framing_concern`, `tally.framing` | flag; `flagged`, `valid`, `threshold`, `proposals[]`, `restatements{}` |
| `conditions[]` | `{seat, condition}` of the seats that voted for the verdict |
| `kill_criteria_for`, `kill_criteria[]` | `{seat, criterion}`, winning side only, at most 20 |
| `unresolved_questions[]` | `{seat, vote, question, source}`: UNKNOWN items of every valid final ballot, at most 20 |
| `usage` | `calls`, `nudges`, `fallback_calls`, `fallback_seats`, `unattended`, `skipped`, `carried`, `rounds_requested`, `rounds_run`, `wall_secs{r1..}`, `total_wall_secs`, `deadline_secs`, `deadline_hit`, `per_seat{calls, nudges, fallback_calls, call_secs}` |
| `seats.<id>.history[].attempts[]` | one entry per CLI process: `round`, `model`, `level`, `kind` (primary, fallback, nudge), `status`, `detail`, `secs` |

Usage counts are telemetry, computed after the tally and never fed into it. A call is a CLI process
that was started (the call before a nudge and the nudge are two calls). `wall_secs` is elapsed time per
round; seats run in parallel, so it is not the sum of call times. No token or cost figures. Round
timings are stored in meta.json, so `tally` reproduces them, together with `min_margin`.

`status --json` prints `state` (STARTING, RUNNING, DONE, TAINTED, FAILED), `verdict`, `decided_by`,
`actionable` (DONE with a verdict), `council_verdict`, `share`, `share_of`, `min_margin`, `narrow_margin`,
`framing_concern`, `framing`, `conditions`, `kill_criteria_for`, `kill_criteria`, `unresolved_questions`,
`unattended`, `usage` (without `per_seat`) and `decision_md`. Exit codes match plain `status`
(0, 4 for TAINTED, 1 for FAILED).

`run --dry-run` goes through the same validation as `run` (options, secret scan, `--default`,
`--min-margin`, `--deadline`, seat ids), resolves seats and prints one JSON object: options, default,
rounds, `timeout_per_call`, quorum, each seat (`primary`, `fallback`, `fallback_dropped`, `cli_found`,
`can_sit`, `reason`, `max_calls`), `skipped`, `sitting`, `quorum_ok`, `discovery_ran`, `prompt_bytes_r1`,
`bounds` and `warnings` (unparsed option lines, seats that cannot sit, NO QUORUM, argv prompts near
32 KB). It creates no run directory and calls no model; seat discovery does run. Bounds, per seat with
`n` models over `r` rounds: `max_calls = 2 x (r + n - 1)` (each model call may get one nudge, and the
level only moves down the chain); `max_wall_secs = rounds run x 2 x max n x timeout`, capped by
`--deadline`. Both exclude discovery, the workspace snapshot/fingerprint and CLI start-up.

## Why this shape (short)

- Independent first answers, then a vote: in "Debate or Vote" (NeurIPS 2025) majority voting
  explains most of multi-agent-debate gains; debate alone does not raise expected correctness,
  but targeted interventions that push belief updates towards correction do. Hence: a blind round,
  one evidence-focused cross-exam, explicit "votes are not evidence, switch only on evidence".
- Anonymized positions: "When Identity Skews Debate" (ACL 2026) shows sycophancy and self-bias
  in debate and removes identity markers; peer review in Karpathy's llm-council relabels answers
  as Response A/B for the same reason.
- Different vendors: same-family agents conform and collapse to consensus (CAIS 2026 study of
  homogeneous teams), so the default council is one seat per vendor family.

See `docs/research.md` in the repo for the full survey.
