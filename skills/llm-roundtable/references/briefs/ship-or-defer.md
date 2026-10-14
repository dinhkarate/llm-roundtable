# Should the new search ranking ship in Thursday's release?

A rewritten ranking for in-app search is ready. Offline evaluation on last month's queries: click-through on the
first result 41% (new) vs 37% (current), measured on 20,000 sampled queries. Latency p95 rose from 180 ms to
240 ms; the product's budget is 300 ms.

Not done yet: an A/B test on live traffic (needs 2 weeks), and a review of 30 queries where the new ranking
put a sponsored item first (the old one never did). The release after Thursday is in 14 days.
Turning the ranking off after release needs a config change and a restart (about 15 minutes).

## Options
- A: Ship to everyone on Thursday
- B: Ship on Thursday behind a flag for 10% of users, review the sponsored-item queries during the test
- C: Defer to the next release and run the A/B test first
