Checks that every registered cron health check is running on schedule by
querying the latest `CheckIn` records in the database.

## What is checked

- **No check-ins at all** — the cron task has never called `check_in`. This
  means the task is not deployed, not registered, or the database has been
  wiped.
- **Overdue** — the latest check-in's start (or end, if finished) plus
  `max_runtime` + `checkin_margin` is in the past and no newer check-in has
  arrived. This means the cron job is running late or has stopped.
- **Consecutive failures** — the latest check-in has state `FAILED` and the
  number of failed check-ins meets or exceeds the cron's
  `failure_issue_threshold`. This means the task is running but consistently
  raising exceptions.

## Possible causes

### Task not deployed

- The package containing the `@procrastinate_task` function was never installed
  or the task was never registered with the procrastinate worker.
- The worker process is not running or has crashed.
- The periodic task scheduler inside procrastinate is not active.

### Task running late

- The task payload is larger than usual (network, data processing).
- A downstream dependency (database, cache, API) is slow.
- The worker queue is congested with higher-priority jobs.
- The system clock is skewed (unusual, but possible in containerised
  environments).

### Task consistently failing

- An upstream service or API is down.
- An expected environment variable or secret is missing.
- The task logic has a bug that only manifests in production data.
- A transient infrastructure issue has not self-resolved within the configured
  threshold.

## Debugging

1. Check the procrastinate dashboard or logs to see whether the task was
   launched and what status it reported.
2. Inspect the `CheckIn` table directly for the offending cron slug:
   `SELECT * FROM whealth_checkin WHERE cron_id = (SELECT id FROM whealth_cron WHERE slug = '<slug>') ORDER BY start DESC LIMIT 5;`
3. Verify the cron's `checkin_margin` and `failure_issue_threshold` settings —
   they may be too tight for the actual runtime.
4. If the task is long-running, consider increasing `max_runtime`.
