# llm-roundtable — agent notes

Multi-model decision council packaged as an Agent Skill. Source of truth for the `llm-roundtable` skill
(installed everywhere through `npx skills` / the pi-skill manifest — never edit installed copies in `~/.agents/skills`).

- Code: `skills/llm-roundtable/scripts/roundtable.py` (Python 3.9 stdlib only; macOS ships 3.9), seats/adapters in `seats.json`.
- Tests: `python3 -m unittest discover -s tests` — uses `tests/fake_cli.py`, no model calls. Keep them green.
- Live check costs quota: `roundtable.py doctor --probe` (~12 tiny calls); a full council ~12 calls / 5-20 min.
- Model names change: update `seats.json` (max two models per seat: primary + one fallback) and the table in `docs/research.md`.
- CLI quirks found so far are in `docs/research.md` §4 — read before touching an adapter.
- Commits: co-author trailer `Co-authored-by: claude-chan <claude-chan@thatnghiep.dev>` when an agent helped.
