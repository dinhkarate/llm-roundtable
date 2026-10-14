# What should we do about the major version upgrade of our HTTP client library?

Our service pins version 2.x of its HTTP client library. Version 3.0 shipped six weeks ago; 2.x gets security
fixes for another 9 months. The 3.0 changelog lists: a new async API, removal of the deprecated `session`
argument (we pass it in 14 places), and a changed default timeout (from none to 30 seconds).

Members can read the lockfile and the call sites in the workspace (`--workspace`), read-only.
Our test suite covers about 60% of the code that makes HTTP calls. No incident is open; nothing forces a date.

## Options
- A: Upgrade to 3.x now, fixing the 14 call sites and setting timeouts explicitly
- B: Stay on 2.x, add a reminder to upgrade before its security support ends
- C: Upgrade in two steps: first set explicit timeouts and stop passing `session` on 2.x, then move to 3.x
