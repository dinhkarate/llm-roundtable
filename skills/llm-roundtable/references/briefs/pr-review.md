# Review: add retry with backoff to the payment webhook handler

Run this brief with `--mode review` (options APPROVE / CHANGES / REJECT are added by the script; this file has
no Options section on purpose) and `--workspace <repo>` so members can read the change, or paste the diff below.

## The change

The webhook handler that receives payment-status callbacks now retries its database write up to 5 times with
exponential backoff (0.2 s doubling, capped at 3 s) when the write fails with a connection error. Before, a
failed write returned HTTP 500 and the payment provider retried the webhook itself after 1 minute.

The handler must answer the provider within 10 seconds or the provider marks the delivery failed.
Writes are keyed by the provider's event id; a duplicate event id is ignored by a unique constraint.

```diff
-    db.save(event)
-    return 200
+    for attempt in range(5):
+        try:
+            db.save(event)
+            return 200
+        except ConnectionError:
+            time.sleep(min(0.2 * 2 ** attempt, 3.0))
+    return 500
```

## What to judge

Whether this change is safe to merge as is, needs changes first, or should not be merged.
