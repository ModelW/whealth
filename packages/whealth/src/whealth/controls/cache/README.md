Calls `get_or_set` with a short TTL on every cache backend configured in `settings.CACHES`. If the operation fails for any backend, a failure is raised using that backend's alias as the key. Each cache is checked independently so a Redis outage doesn't mask a healthy Memcached or local-memory backend.

## Possible causes

### Managed PaaS (e.g. Render, Heroku, Fly.io, Railway with managed Redis / Upstash / KeyDB)

- The managed Redis instance has been stopped or throttled due to plan limits.
- The connection string or password was rotated but the app still holds the old value.
- The maximum number of concurrent connections has been reached (common on smaller tiers).
- A maintenance window or failover is in progress.

### Docker Compose

- The Redis / Memcached container has crashed or hasn't finished starting yet.
- The service name or port in the Compose file differs from what Django expects.
- No `healthcheck` is configured on the cache container, so Docker reports it as "started" before it's ready.
- The container ran out of memory and was OOM-killed.

### Generic

- Network latency or a firewall rule is blocking the cache port.
- The cache server is running but TLS is enabled while the client expects a plaintext connection (or vice versa).
- The cache has hit its `maxmemory` limit and is evicting aggressively, causing `get_or_set` to fail.
- A DNS resolution failure is preventing the client from reaching the cache host.
- The cache backend does not support `get_or_set` directly (e.g. a minimal file‑based backend).
