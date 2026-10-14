# Changelog

## 0.1.0 (2026-10-14)

First public release.

- Six-seat council across five vendors: Claude Fable, Claude Opus, GPT (Codex CLI), Grok, Gemini (Antigravity), newest free OpenCode model.
- Blind round + anonymous cross-exam, evidence-rated weighted vote, Fable tie-break, safe `--default`.
- One-level fallback per model family, then UNATTENDED.
- Review mode for plans, diffs and PRs (`APPROVE / CHANGES / REJECT`).
- Read-only, sandboxed seats; publishing tools removed; credentials stripped; workspace tamper check.
- Survives host sleep and stop signals; `status` for detached runs.
- `npx llm-roundtable` wrapper.
