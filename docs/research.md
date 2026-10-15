# Research: a decision council of AI models

[Tiếng Việt](research.vi.md) · Started 2026-10-13 by Claude (Opus 5.5) in an Orca session; kept up to date as the project changes.

## 1. Prior art

"Several models answer, grade each other, then synthesise or vote" is a crowded idea. No existing project
combined everything this one needed: CLI subscriptions instead of API keys, four or five vendors, a strict
one-level fallback followed by UNATTENDED, votes weighted by peer-rated evidence, a fixed tie-breaker,
and a skill that runs from any agent host.

| Project | How it calls models | Mechanism | What it lacks for this use |
|---|---|---|---|
| [karpathy/llm-council](https://github.com/karpathy/llm-council) | OpenRouter API | answer → anonymous ranking (Response A/B) → chairman synthesises | web app, needs an API key; a chairman writes the answer instead of a vote |
| [0xNyk/council-of-high-intelligence](https://github.com/0xNyk/council-of-high-intelligence) (~4.6k★ in Oct 2026, MIT) | Claude subagents + `codex exec`, `gemini -p`, ollama, cursor-agent | 18 personas, restate → blind analysis → anonymised cross-exam → STANCE/CONFIDENCE/DEALBREAKER; confidence-weighted tally needing 2/3, then a chairman writes the verdict; runs on Claude Code, Codex, Gemini CLI, OpenCode | closest match; the protocol is prose the host model follows (not enforced code), evidence labels are not enforced, falls back to Claude on errors, escalates splits to the user, no Grok/agy |
| [Max-aiutopia/llm-council](https://github.com/Max-aiutopia/llm-council) (MIT) | `codex`, `agy`, `grok` (subscriptions) | parallel answers in an empty directory, privacy gate, Claude writes the decision | no cross-exam, no vote; Claude decides alone |
| [BeehiveInnovations zen / PAL MCP](https://github.com/BeehiveInnovations/zen-mcp-server) | provider APIs; `clink` calls other CLIs | `consensus` tool, multi-model conversation | an MCP server installed per host; no vote or tie rule |
| npm [`roundtable`](https://github.com/umutc/roundtable), [`roundtable-cli`](https://github.com/vladagurets/roundtable) | Claude Code agents / local CLIs | debate, moderator synthesises | single vendor or no evidence-weighted vote |
| hex claude-council, xrf9268 llm-council-plugin, sherifkozman/llm-council, polyclaude, design-council, maestro, gavel, frahlg/fusion, openfusion | APIs or CLIs | parallel + synthesis, role debate, judge + synthesiser | mostly Claude Code only; a judge synthesises instead of an evidence-based vote |

Conclusion: **no fork.** Borrow three proven ideas (independent first round, anonymous review, evidence
labels) and write the rest: one-level fallback, UNATTENDED seats, weights from peer-rated evidence, Fable
as tie-breaker, any host.

## 2. What the literature says about debate and voting

1. **Debate or Vote** (Choi, Zhu, Li, NeurIPS 2025): most of the benefit of multi-agent debate comes from
   *majority voting*; debate by itself does not raise expected correctness (the belief process is a
   martingale). Targeted interventions that push updates toward correction do help.
   → Keep an independent round 1 and a vote; only one cross-exam round by default, and it is bound to
   evidence ("vote counts are not evidence; change your vote only when a specific piece of evidence forces it").
2. **When Identity Skews Debate** (ACL 2026): debaters show sycophancy (siding with peers) and self-bias
   (defending their own answer); anonymising answers reduces both. → Cross-exam uses M1..Mn, shuffled,
   in a new session each round, so a model really cannot tell which answer was its own; self-ratings are dropped.
3. **Homogeneous teams** (CAIS 2026): agents of one model family follow the majority (up to 85.5% accept
   the majority answer), collapse into consensus and cost 2-3× the tokens of self-correction. → One seat
   per model family by default; the `solo-*` presets warn and recommend adding OpenCode for another vendor.
4. Karpathy reports that models in llm-council tended to praise GPT and criticise Claude, sometimes against
   his own judgement. → No chairman model writes or judges the result; the verdict is arithmetic on
   ballots and the host only reports it.

## 3. Design

- **One pure Python script (stdlib, 3.9+) plus an Agent Skills `SKILL.md`.** Any host with a shell
  (Claude Code, Codex, Grok CLI, Antigravity, OpenCode, pi) can run it; no MCP, no Orca required.
  Installed with `npx skills` like any other skill, or run through the `llm-roundtable` npm wrapper.
- **Each seat is a headless CLI process with a fresh session** (read-only for the default seats; the opt-in
  OpenCode seat is not sandboxed), in an empty temp directory
  (default) or reading the repo with `--workspace`. Adapters are JSON, so a new CLI (qwen, cursor-agent,
  pi...) needs no code change.
- **Default seats:** fable `claude-fable-5-1`, opus `claude-opus-5-5`, codex `gpt-6.1-sol`, grok `grok-4.7`,
  gemini `gemini-3.8-flash-high` (via agy): five seats from four vendors. The free OpenCode seat (the newest free
  model from a family not already seated) was a default until v0.2.0; it is opt-in (`full-open`, solo presets)
  since the release review found it is not sandboxed. With six seats, or whenever one seat drops out, the count
  is even, so "ties go to Fable" matters.
- **One-level fallback**, then UNATTENDED. A fallback that equals another seat's primary is skipped.
- **Votes:** at least one FACT or INFERENCE item with a source, otherwise the ballot does not count.
  Weight = seat weight × (0.5 + 0.5 × mean evidence rating from the other seats, 0-2). Highest weighted
  score wins; tie → Fable's choice; Fable outside the tied group → TIE. Fewer than 2 valid ballots →
  NO QUORUM. TIE / NO QUORUM → `--default`. `decision_rule: "count"` switches to a plain count.
- **Safety:** secret-looking briefs are blocked; `--private` drops seats that may train on prompts
  (OpenCode free); `ROUNDTABLE_SEAT` stops nested councils; the host may not "fix" the result.

## 4. Field notes

`roundtable.py doctor --probe` on the author's machine (2026-10-13):

| Seat | Primary | Fallback |
|---|---|---|
| fable | claude-fable-5-1 ok | claude-fable-5 ok |
| opus | claude-opus-5-5 ok | claude-opus-5 ok |
| codex | gpt-6.1-sol ok | gpt-6-sol ok |
| grok | grok-4.7 ok | grok-4.6 ok |
| gemini (agy 1.3.4) | gemini-3.8-flash-high ok | gemini-3.7-flash-high **not offered by agy** → when 3.8 is out of quota the seat is UNATTENDED |
| opencode | opencode/muse-spark-1.3-contributor-free ok (2026-10-15, preferred: cat-jam-free gave weak ballots) | opencode/cat-jam-free ok (2026-10-12); exo-free **deprecated** → recorded in dead-models automatically |

CLI quirks found while building it (read these before touching an adapter):

- `opencode run` hangs if stdin stays open → the script always passes `/dev/null`.
- `agy --mode plan` in print mode waits for plan approval and is cancelled → `--sandbox --disable-slash-commands`.
  Not `--dangerously-skip-permissions`: it can lift the sandbox (agy issue #36). Headless agy therefore
  denies prompt-gated tools such as `read_url`, and with `--workspace` it reads a snapshot copy, never the real checkout.
- `grok -p` swallows the next flag as the prompt when it comes first → `--prompt-file`.
- models.dev returns 403 without a User-Agent → the script sends one and caches for a day.
- grok-4.7 refuses "reply with exactly ..." prompts → probes ask a real question.
- `opencode models` sometimes returns nothing while its background service starts → retry with `--standalone`.
- grok-4.7 sometimes says "I'll read the files first..." and ends its turn → any seat that returns no
  ballot is re-asked exactly once to print the JSON ballot (not counted as a fallback).
- A relative `--out` made grok miss its prompt file (different cwd) → every path is resolved absolute.
- Laptop lid closed on battery (run 4, 2026-10-13 18:02-20:00): the machine kept entering Maintenance
  Sleep, seats hung without network, and timeouts never fired because `communicate(timeout)` uses the
  monotonic clock (frozen during sleep) → wall-clock deadlines, a "host slept Ns" log line, and
  `caffeinate -i -s` during the run (which cannot prevent lid-close sleep on battery).
- SIGTERM with `sys.exit` let worker threads see dead seats and start fallback models → a stop flag plus `os._exit`.
- OpenCode prints files it read to stderr; one file containing the word "quota" turned a network error
  into "out of quota" → only the last 15 lines are matched.
- Plan modes inject "spawn agents, ExitPlanMode" instructions into claude and end grok's headless runs
  before the ballot → neither CLI runs in plan mode; read-only comes from allowlists and sandboxes.
- The opencode seat ran its shell commands in the *caller's* directory: opencode takes its project from `$PWD`,
  which seats inherited (2026-10-14 v0.2 councils: it listed the other briefs and the batch script) → seats get
  `PWD` set to their sandbox. opencode's `plan` agent can still run shell commands; config-level denies are
  ignored because `opencode run` talks to an already-running background service, and `--standalone` refuses
  free models. Treat the opencode seat as able to read the machine; `--private` drops it.
- Codex kills every process a shell tool call started when the call returns, so `nohup ... &` from a Codex host
  never finished a council (2026-10-14 host test) → `run --detach` double-forks into its own session.
- `status` used to end at `DONE` without the verdict, so host agents re-ran `tally` to read it → `status` now
  prints the `VERDICT:` line.
- A claude seat inherited the user's Claude Code setup: a SessionStart hook added context listing vault secret
  *names*, a UserPromptSubmit hook ran, and auto-memory was attached (seen with `--include-hook-events`,
  2026-10-14). That context could be quoted in a ballot and forwarded to four other vendors → claude seats run
  with `--restricted`, which ignores user/project/local settings: no hooks, no memory paths, about 1.4k fewer
  input tokens per call. The allowlisted `ls` still works under `--restricted`.
- "You've hit your session limit" from claude is account-wide: walking to `claude-fable-5` on the same account
  wasted 10 calls in the v0.2 councils → account-level patterns skip the fallback.
- agy answered `PERMISSION_DENIED (code 403): This service has been disabled in this account for violation of
  Terms of Service` on the author's machine (2026-10-14, `agy models`), after the gemini seat had been UNATTENDED
  (quota) in every v0.2 council → treated as account-level. Model calls the next day returned 429 quota
  (`Resets in 104h`) rather than 403, so the block may cover the model listing only. agy's JSON output format
  could not be inspected, so the agy adapter stays plain text and reports no tokens.
- Token figures come from each CLI's JSON output (`claude --output-format json`, `codex exec --json`,
  `grok --output-format json`, `opencode run --format json` + `opencode session export <id>`; opencode's run
  output itself carries none). The input side dominates: on a one-round smoke council about a formatter's line
  length (2026-10-14) the four seats used 259k tokens, 64% of them cache reads, and grok alone 120k (it reads and
  searches before voting).
- Codex ships 100+ `codex_apps` tools (deploy sites, share pages, Datadog) plus computer use, and claude
  may load MCP servers that publish externally → all of these are disabled for council seats.

The first real council (brief: should this skill live in its own repo or inside the author's skill
monorepo?) → 4/4 valid ballots chose its own repo; Fable, Opus and Codex cited the vercel-labs/skills
README and the GitHub Actions docs as evidence.

### The council reviews itself (`--mode review --workspace <repo>`)

| Run | Commit | Valid ballots | Verdict | What the council found (each with a reproducing command) |
|---|---|---|---|---|
| run2 | 86d73a5 | 5/6 (grok invalid) | CHANGES 5/5 | claude plan mode injected "spawn agent / ExitPlanMode"; the count rule ignored scores on ties; list-shaped ratings crashed the run; unsourced FACTs still counted; the parser picked nested objects; `status` stuck at RUNNING; the tally lost the workspace flag |
| run3 | b53803e | 6/6 | CHANGES 6/6 | `status` reported an old run's DONE while a new one was starting; the claude allowlist allowed code execution (`unittest`, `rg --pre`, `git diff --output`); agy was read-only only by prompt; the sandbox inside the run dir exposed the label table (breaking anonymity); ratings applied to ballots that had switched sides; unsourced INFERENCE; wrong dissent on TIE; `fill()` replaced nested placeholders; processes not cleaned up when killed |
| run5 | dae30ee | 5/6 (gemini unattended, quota) | CHANGES 5/5 | ballots read from stderr or echoed tool output; a tainted workspace still produced a verdict; agy's `--dangerously-skip-permissions` could lift its sandbox; seats inherited unrelated credentials; invalid ballots could rate peers (fixed in 85dc1e2) |

## 5. Open work

- Orca transport: each seat as its own Orca agent terminal (visible TUIs, seats on other machines).
- Remote seats over SSH: an adapter like `ssh host claude -p ...`.
- Compare the `count` and `weighted` rules on a question set with known answers, and pick the default from data
  (`outcome` + `ledger` collect the data from real use).
- Early stop as a default: `ledger` on the author's 15 runs (2026-10-15): of 12 runs that cross-examined, 5 had a
  unanimous round 1 and none of those changed a vote in round 2. Too few runs to flip the default yet.
- Retry or resume for UNATTENDED seats (a quota blip currently loses the seat for the run).
- The Gemini seat: on the author's account `agy models` answers 403 and gemini 3.8 is out of quota, so a
  replacement fallback cannot be verified here.

## Sources

- [karpathy/llm-council](https://github.com/karpathy/llm-council) · [explainer (Analytics Vidhya)](https://www.analyticsvidhya.com/blog/2025/12/llm-council-by-andrej-karpathy/)
- [0xNyk/council-of-high-intelligence](https://github.com/0xNyk/council-of-high-intelligence) · [write-up](https://explainx.ai/blog/council-of-high-intelligence-multi-llm-deliberation-claude-code-2026)
- [Max-aiutopia/llm-council](https://github.com/Max-aiutopia/llm-council)
- [Claude Code council plugins compared](https://www.claudepluginhub.com/blog/claude-council-plugins-compared)
- [Zen / PAL MCP server](https://mcpservers.org/de/servers/BeehiveInnovations/zen-mcp-server)
- [Debate or Vote (arXiv 2508.17536)](https://arxiv.org/abs/2508.17536v1) · [NeurIPS 2025](https://neurips.cc/virtual/2025/poster/116557)
- [When Identity Skews Debate (arXiv 2510.07517)](https://arxiv.org/abs/2510.07517) · [ACL 2026](https://preview.aclanthology.org/ingest-acl/2026.acl-long.650/)
- [Decomposing sycophancy, fragility, consensus collapse and cost in homogeneous multi-agent teams (CAIS 2026)](https://caisconf.org/program/2026/papers/decomposing-sycophancy-fragility-consensus-collapse-and-cost-in-homogeneous-mult/)
- [Debate diversity collapse (blog)](https://tianpan.co/blog/2026/04/26/debate-diversity-collapse-multi-agent-ensemble)
- [models.dev](https://models.dev) (OpenCode model release dates)
