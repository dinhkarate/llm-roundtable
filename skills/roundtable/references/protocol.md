# Protocol

## Roles

- **Moderator**: the agent the user is talking to. Writes the brief, runs the script, reports.
  Does not vote, does not edit ballots.
- **Seats**: one CLI process per member per round, fresh session each time (`--ephemeral`,
  `-p`), read-only and without publishing tools:

  | CLI | Read-only by | Outward tools removed |
  |---|---|---|
  | claude | `--permission-mode dontAsk` + allowlist (Read/Grep/Glob/Web*, read-only Bash, `python3 -m unittest`) | `--strict-mcp-config` (no MCP servers), `--tools` without Agent |
  | codex | `-s read-only` sandbox (kernel) | `--disable apps computer_use browser_use` |
  | grok | `--sandbox read-only` (kernel; temp dirs stay writable) | no MCP configured |
  | agy | `--sandbox` (terminal only) + prompt; skip-permissions so headless web reads work | no MCP configured |
  | opencode | `--agent plan` | no MCP configured |

  Plan modes are avoided on claude and grok: they inject "write a plan, exit plan mode" instructions
  and end headless runs before the ballot. Each call gets `ROUNDTABLE_SEAT=<id>` so a seat that loads
  this skill cannot start a nested council. With `--workspace`, the script fingerprints the git
  checkout (HEAD, status, diff, untracked file hashes) before and after; any change gives a WARNING
  banner and exit code 3. Secret-looking strings that seats quote are redacted before the
  cross-exam dossier goes to the other vendors.

## Rounds

| Round | Members see | Members return |
|---|---|---|
| 1 (blind) | brief + options | vote, confidence, summary, evidence[], risks, conditions |
| 2..3 (cross-exam) | brief + every previous position as M1..Mn, shuffled, own one unmarked | same + ratings{Mi: 0-2}, rebuttals[], decisive_evidence[] |

Default 2 rounds. Each cross-exam round is a new session, so a member does not remember its own
earlier answer; the anonymity is real, not a request to "please ignore names".

Evidence types: `FACT` (verified, with a source), `INFERENCE` (reasoned from cited facts),
`ASSUMPTION` (unverified). A ballot needs at least one FACT or INFERENCE item to count
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
peer(seat)   = mean of the 0-2 ratings other members gave it in the last cross-exam (1.0 if none)
weight(seat) = seat.weight x (0.5 + 0.5 x peer)          -> 0.5x .. 1.5x
score(opt)   = sum of weight over valid ballots for opt
verdict      = argmax score                               (decision_rule "count": argmax votes, score breaks ties)
tie          -> option the tiebreak seat (Fable) voted for; Fable not on a tied option -> TIE, ask the user
valid ballots < quorum (2) -> NO QUORUM
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
