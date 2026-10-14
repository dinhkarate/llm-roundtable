# Sample briefs

Five briefs that show the shape a council needs. Copy one, replace the facts with yours, keep the structure.
The whole file becomes the members' prompt, so a brief holds only the question, the facts and the options:
no hints about which option you prefer, no expected answer.

| Brief | Mode | Shows |
|---|---|---|
| [database-choice.md](database-choice.md) | decide | a technology choice with numbers members can check |
| [schema-migration.md](schema-migration.md) | decide | a risky change with a "do it in steps" option and a reversible default |
| [dependency-upgrade.md](dependency-upgrade.md) | decide | upgrade now / pin / replace, with `--workspace` so members read the lockfile |
| [ship-or-defer.md](ship-or-defer.md) | decide | ship, ship behind a flag, or defer; "defer" as a real option |
| [pr-review.md](pr-review.md) | review | approval of a change: no `## Options` section, the script adds APPROVE / CHANGES / REJECT |

## Running one

```bash
S=<skill dir>/scripts/roundtable.py
python3 $S run --brief references/briefs/database-choice.md --default A --dry-run   # plan only, no model call
RUN=$(python3 $S run --brief my-brief.md --default A --detach)
python3 $S status "$RUN"
```

`--default` must be one of the option ids the brief defines (`A`, `B`, ...). Pick the safest, most reversible
one: it is what happens on a tie, a narrow margin or no quorum. Review mode defaults to `CHANGES`.

For `pr-review.md`, either paste the diff into the brief or pass `--workspace <repo>` so members read the
change themselves (read-only), and add `--mode review`.

## What comes back (shape, not answers)

- Last line: `VERDICT: <option|NONE> (council|tiebreak|default|none|workspace_changed)`.
- Lines before it (only when they apply): `USAGE:` (calls, tokens, wall time), `MARGIN:`, `EARLY STOP:`,
  `INJECTION:`, `FRAMING:`.
- `decision.md` in the run directory: verdict, tally, evidence for the winner, dissent, conditions to carry out,
  kill criteria, unresolved questions, risks, usage table.
- `result.json` (`schema_version: 2`) and `status --json` for hosts that parse instead of read.

These files are examples of brief structure, not a test set with known answers: they hold no expected verdicts,
and a council's answer to them depends on the models of the day.
