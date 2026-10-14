# Hosts and setups

The council is a plain Python script that shells out to agent CLIs, so it runs from any host
agent with a shell tool. Install the skill for every agent with
`npx skills add dinhkarate/llm-roundtable --skill llm-roundtable` (or through the pi-skill manifest).

Claude Code only, optional: the same skill as a plugin, from this repo's marketplace
(`/plugin marketplace add dinhkarate/llm-roundtable`, then `/plugin install llm-roundtable@llm-roundtable`).
It appears as `/llm-roundtable:llm-roundtable`. Install one or the other, not both, or the skill loads twice.
Unattended agents and CI should use `npx skills add`: it is the same files for every host.

## Running from each host

Every host starts the council with `--detach`, because a council outlives tool timeouts and some hosts
kill whatever a tool call started once the call returns (Codex does; `nohup ... &` does not survive it):

```bash
python3 $S run --brief brief.md --dry-run         # preflight: seats, quorum, bounds as JSON; nothing is created
RUN=$(python3 $S run --brief brief.md --detach)   # the run directory; the council continues in its own session
python3 $S status "$RUN"                          # STARTING / RUNNING / DONE / TAINTED / FAILED, then VERDICT: ...
python3 $S status --json "$RUN"                   # the same as one JSON object (state, verdict, flags)
```

The dry run still resolves the OpenCode seat (`opencode models`, up to a few minutes when its service is
slow). A bad `--seats` now fails before `--detach`, on the caller's stderr.

| Host | Waiting |
|---|---|
| Claude Code | a background `until python3 $S status "$RUN" \| grep -qE '^(DONE\|TAINTED\|FAILED)'; do sleep 30; done`, re-armed if it times out |
| Codex CLI, Grok CLI, Antigravity, OpenCode, pi | call `status "$RUN"` every 1-2 minutes (Antigravity: a 60 s timer works) |
| Orca | either of the above, or run the council in its own Orca terminal so the user can watch `progress.log` |

`$S` = `<skill dir>/scripts/roundtable.py`. `python3 $S doctor` shows which seats this host can fill.

## Where each host finds the skill

Tested 2026-10-14 by asking each CLI, headless, to find the skill and run a `duo` council:

| Host | Skill found at | Notes |
|---|---|---|
| Claude Code | `~/.claude/skills/llm-roundtable` (symlink to `~/.agents/skills`) | listed as a skill |
| Codex CLI | `~/.agents/skills/llm-roundtable` | needed `--detach`: Codex killed the `nohup` runner when the tool call returned |
| Grok CLI | `~/.grok/skills/llm-roundtable` | listed as a skill |
| OpenCode | `~/.agents/skills/llm-roundtable` | loaded through its Skill tool |
| Antigravity (agy) | `~/.agents/skills/llm-roundtable` | not listed among agy's skills; agy found it by searching the filesystem |
| Claude Code plugin | plugin cache, root `skills/llm-roundtable` of this repo | loaded as `llm-roundtable:llm-roundtable` (checked with `--plugin-dir`, 2026-10-14) |

## Logins each seat needs

| Seat | CLI | One-time login |
|---|---|---|
| fable, opus | `claude` | `claude` (subscription) |
| codex | `codex` | `codex login` (ChatGPT plan) |
| grok | `grok` | `grok login` |
| gemini | `agy` | run `agy` once (an account the provider has disabled answers 403 PERMISSION_DENIED: the seat is UNATTENDED and skips its fallback) |
| opencode | `opencode` | none for free models |

Missing CLIs are not errors: those seats become UNATTENDED and the rest still vote.

## Single-tool setups

| Only this is installed | Preset | What you get | Caveat |
|---|---|---|---|
| Claude Code | `duo` | Fable 5.1 vs Opus 5.5, Fable breaks ties | same vendor; with 2 seats any split is decided by Fable |
| Codex | `solo-codex` | gpt-6.1-sol + gpt-6-sol + free OpenCode model | the two GPT seats share training; add OpenCode for real diversity |
| Grok CLI | `solo-grok` | grok-4.7 + grok-4.6 + free OpenCode model | same as above |
| Antigravity | `solo-agy` | Gemini 3.8 Flash + free OpenCode model | also add Claude/GPT-OSS seats agy offers via a user config |
| OpenCode | custom | several free models from different labs (`"count": 3`) | free models may train on prompts: never with private data |

Recommendation: wherever possible keep at least three different vendor families. Installing
`opencode` is the cheapest way to add one (free models, no login).

## Orca (optional)

Orca is not required. With Orca the user can watch the council: open a terminal in the worktree,
run the council there, and read it with `orca terminal read --screen`. A later version may add an
Orca transport that starts every seat as its own Orca agent terminal (visible TUIs, remote hosts
such as a Windows box) instead of a subprocess.

## Config overrides

Put a JSON file at `~/.config/roundtable/seats.json` (or pass `--config`). Same shape as
`scripts/seats.json`; `adapters` and `presets` merge by key, `seats` patch by `id`, new ids are added.

```json
{
  "seats": [
    {"id": "opencode", "count": 2},
    {"id": "fable", "weight": 1.2},
    {"id": "qwen", "adapter": "qwen", "family": "qwen", "models": ["qwen3-coder-plus"], "weight": 1.0}
  ],
  "adapters": {"qwen": {"bin": "qwen", "argv": ["-m", "{model}", "-p", "{prompt}"]}},
  "presets": {"full": ["fable", "opus", "codex", "grok", "gemini", "opencode", "qwen"]}
}
```

Adapter placeholders: `{model}`, `{prompt}` (text in argv), `{prompt_file}`, `{out_file}`.
`"stdin": true` pipes the prompt on stdin; `"output": "out_file"` reads the answer from `{out_file}`.
Keep `models` to at most two entries: the script never falls back more than one level.
Windows hosts: prefer stdin or `{prompt_file}` adapters; argv prompts hit the 32 KB command-line limit.
