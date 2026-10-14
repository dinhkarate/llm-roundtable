# llm-roundtable — agent notes

Multi-model decision council packaged as an Agent Skill. Source of truth for the `llm-roundtable` skill
(installed everywhere through `npx skills` / the pi-skill manifest — never edit installed copies in `~/.agents/skills`).

- Code: `skills/llm-roundtable/scripts/roundtable.py` (Python 3.9 stdlib only; macOS ships 3.9), seats/adapters in `seats.json`.
- Tests: `python3 -m unittest discover -s tests` — uses `tests/fake_cli.py`, no model calls. Keep them green.
- Live check costs quota: `roundtable.py doctor --probe` (~12 tiny calls); a full council ~12 calls / 5-20 min.
- Model names change: update `seats.json` (max two models per seat: primary + one fallback) and the table in `docs/research.md` (English; `research.vi.md` is the Vietnamese original).
- Public docs: `README.md` (English, SEO/GEO), `README.vi.md`, `llms.txt`; keep the three consistent when behaviour changes.
- npm package `llm-roundtable` is a thin wrapper (`bin/llm-roundtable.js`); bump `package.json` version, then `npm publish --access public`. The account has 2FA: in a non-TTY shell npm prints an auth URL and exits, so run it under `script -q <log> npm publish ...` in the background and hand the user the `npmjs.com/auth/cli/...` link.
- CLI quirks found so far are in `docs/research.md` §4 (Field notes) — read before touching an adapter.
- Commits: co-author trailer `Co-authored-by: claude-chan <claude-chan@thatnghiep.dev>` when an agent helped.
