# Contributing

Thanks for helping. The most useful contributions are new seat adapters, CLI quirks you ran into, and
bug reports with the `progress.log` of the run.

## Ground rules

- `skills/llm-roundtable/scripts/roundtable.py` stays **Python 3.9, standard library only** (it is what macOS ships).
- Keep tests green and free: `python3 -m unittest discover -s tests` uses `tests/fake_cli.py` and never calls a model.
- A live check costs quota: `roundtable.py doctor --probe` makes about 12 tiny calls; a full council about 12 calls.
- Read the CLI quirks in [`docs/research.md` §4](docs/research.md#4-field-notes) before touching an adapter.
- Seats must stay read-only and unable to publish. Any change that widens what a seat can do needs a test.

## Adding a CLI as a seat

Most CLIs need no code: add an adapter and a seat to `~/.config/roundtable/seats.json` (see
[`references/hosts.md`](skills/llm-roundtable/references/hosts.md#config-overrides)), run `doctor --probe`,
then open a PR moving it into `scripts/seats.json` with:

1. how the CLI is made read-only (sandbox flag, tool allowlist) and which outward tools are disabled;
2. the quota / unavailable error text it prints, so the fallback logic can classify it;
3. at most two models (primary + one fallback in the same family).

## Model names

Model names change often. Update `scripts/seats.json` and the table in `docs/research.md` together.

## Reporting a bug

Include the OS, the CLI versions (`claude --version`, `codex --version`...), the command you ran, and
`progress.log` from the run directory. Do not paste briefs that contain private data.
