# Example `decision.md`

> **Illustrative.** The layout below is exactly what `roundtable.py` writes; the question, evidence and
> numbers are a made-up but realistic example, shortened for reading. Real runs also save every seat's
> raw transcript in `r1/`, `r2/` next to this file.

---

# Roundtable: Which database should the billing service use?

**Verdict: B: SQLite with Litestream backups**  (weighted 5.25 of 6.75, 4 of 5 valid votes)

Rule: weighted vote; weight = seat weight x (0.5 + 0.5 x mean peer evidence rating 0-2); ballots without FACT/INFERENCE evidence do not count; ties go to the Fable seat.

## Tally

| Option | Weighted | Votes | Seats |
|---|---|---|---|
| A: PostgreSQL | 1.50 | 1 | opus |
| B: SQLite with Litestream backups | 5.25 | 4 | fable, codex, grok, opencode |
| C: Defer: keep the JSON files for another month | 0.00 | 0 | - |

## Seats

| Seat | Model | Status | Vote | Conf. | Peer evidence | Weight | Path |
|---|---|---|---|---|---|---|---|
| fable | claude-fable-5-1 | ok | B | 0.71 | 1.75 | 1.38 | r1 ok / r2 ok |
| opus | claude-opus-5-5 | ok | A | 0.58 | 2.0 | 1.50 | r1 ok / r2 ok |
| codex | gpt-6.1-sol | ok | B | 0.74 | 1.75 | 1.38 | r1 ok / r2 ok |
| grok | grok-4.7 | ok | B | 0.66 | 1.5 | 1.25 | r1 ok / r2 ok |
| gemini | - | UNATTENDED | - | - | - | 0.00 | r1 unattended |
| opencode | opencode/cat-jam-free | ok | B | 0.60 | 1.5 | 1.25 | r1 ok / r2 ok |

## Unattended

- **gemini**: gemini-3.8-flash-high: quota; gemini-3.7-flash-high: unavailable

## Changed votes

- **grok**: A -> B because: M4: 40k writes/day is about 0.5 writes/s; SQLite in WAL mode handles that on one VPS with room to spare, and the brief rules out a second region.

## Evidence for B

- **codex**: The workload is small, single-region and single-host; SQLite removes a server to operate for a team of three, and Litestream gives continuous off-site backups.
  - [FACT] The brief states 40k writes/day, one region, a single VPS and a team of 3. (brief.md:3)
  - [FACT] Litestream streams SQLite WAL changes to S3-compatible storage and restores to a point in time. (https://litestream.io/how-it-works/)
  - [INFERENCE] 40k writes/day ≈ 0.46 writes/s average; even a 50× peak stays far below a single SQLite writer's limits. (brief.md:3)
- **fable**: ...

## Dissent

- **opus** voted A: billing data tends to grow reporting and concurrent-access needs; migrating later costs more than starting on PostgreSQL now.
  - [FACT] PostgreSQL supports concurrent writers and row-level locking; SQLite allows one writer at a time. (https://www.sqlite.org/lockingv3.html)

## Conditions attached to B (carry these out with it)

- (fable) Enable WAL mode and test a Litestream restore before going live.
- (codex) Keep data access behind one module so a later move to PostgreSQL is a contained change.
- (grok) Revisit if a second region or a second writer service appears.

Run finished 2026-10-14T12:05:20. Full transcripts: r1/, r2/ ... next to this file.
VERDICT: B (council)
