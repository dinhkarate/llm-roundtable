# Security audit of the session and password-reset code

Scope: `src/auth/` (session cookies, login, password reset) and the routes that call it in `src/routes/account.ts`.
Out of scope: the admin panel, front-end code, infrastructure.

Context: a Node 22 / Express service, sessions in Redis, passwords hashed with bcrypt (cost 12). The reset flow
emails a token link valid for 30 minutes. The service is public; about 40k active accounts.

Look for problems an attacker could use or that could lock users out: token handling, session fixation,
missing rate limits, timing leaks, unsafe redirects, secrets in code or logs. Report each problem with the
file and line that shows it; say what you could not check (for example, configuration that is not in the repo).
