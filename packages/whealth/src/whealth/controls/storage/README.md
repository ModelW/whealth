Calls `exists()` on a sentinel path for every storage backend configured in `settings.STORAGES`. If the call fails for any backend, a failure is raised using that backend's alias as the key. Each storage is checked independently so an S3 outage doesn't hide a healthy local filesystem.

## Possible causes

### Managed PaaS (e.g. Render, Heroku, Fly.io, Railway with S3 / R2 / GCS / MinIO)

- The bucket or container has been deleted or the access policy has been revoked.
- The access key or secret was rotated but the environment variables still reference the old pair.
- The bucket is in a different region and the client does not have cross-region access configured.
- The service enforces request signing (AWS Signature V4) and the client library is misconfigured.
- An S3 life‑cycle policy or object lock is interfering with the `exists()` check.

### Docker Compose

- The MinIO (or equivalent) container has not finished initialising or has crashed.
- The bucket has not been created yet (MinIO does not auto‑create buckets like S3 does).
- The endpoint URL points to the wrong port or service name.
- The access credentials in `docker-compose.env` do not match the MinIO instance.

### Generic

- A transient network error interrupted the request to the storage endpoint.
- The storage service is down for maintenance or is throttling the application.
- TLS/SSL certificate validation is failing because the endpoint uses a self‑signed certificate.
- The path or key format expected by `exists()` is rejected by the storage backend (e.g. S3 key length limits).
- A corporate proxy or VPN is intercepting or blocking traffic to the storage endpoint.
