# How should we rename the `users.email` column to `users.login_email`?

The main application (one PostgreSQL 16 database, ~12 million rows in `users`) is deployed several times a day
by CI with rolling restarts: during a deploy, old and new application versions run side by side for up to
10 minutes. Three internal services also read `users.email` directly; their owners need a week's notice.

The rename is wanted because a second, unverified "contact email" column is coming next quarter and the current
name will be ambiguous. Nothing breaks today if we wait.

## Options
- A: Expand/contract over several deploys: add `login_email`, dual-write, backfill in batches, move readers, then drop `email`
- B: One migration with `ALTER TABLE users RENAME COLUMN` and a coordinated deploy of all four codebases
- C: Keep the column name; add a view or a comment and name the new column `contact_email` instead
- D: Defer until the contact-email work starts next quarter
