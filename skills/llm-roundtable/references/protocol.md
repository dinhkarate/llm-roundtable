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
  | opencode | `--agent plan` | no MCP configured |

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
| 1 (blind) | brief + options | vote, confidence, summary, evidence[], risks, conditions |
| 2..3 (cross-exam) | brief + every previous position as M1..Mn, shuffled, own one unmarked | same + ratings{Mi: 0-2}, rebuttals[], decisive_evidence[] |

Default 2 rounds. Each cross-exam round is a new session, so a member does not remember its own
earlier answer; the anonymity is real, not a request to "please ignore names".

Evidence types: `FACT` (verified, with a source), `INFERENCE` (reasoned from cited facts),
`ASSUMPTION` (unverified). FACT or INFERENCE items without a source are downgraded to ASSUMPTION.
A ballot needs at least one FACT or INFERENCE item to count
(`no_evidence` otherwise). A vote that is not one of the option ids is `invalid`.

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
TIE / NO QUORUM -> --default (safe option from the brief; review mode: CHANGES), else VERDICT NONE
```

Confidence is recorded but not weighted: self-reported confidence is poorly calibrated and easy to
inflate. Peer-rated evidence is the weight because that is what the user asked the council to
argue over.

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
