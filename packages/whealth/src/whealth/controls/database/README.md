Executes a `SELECT 1` query on every configured database from `settings.DATABASES`. If the query fails for any database, a failure is raised using that database's alias as the key. Each database is treated independently — one broken replica won't hide the fact that others are healthy.

## Possible causes

### Managed PaaS (e.g. Render, Heroku, Fly.io, Railway)

- The database service has been paused due to inactivity (common on free-tier plans).
- The connection pool is exhausted because long-running queries are holding connections open.
- A planned maintenance window or automated failover is in progress.
- The database credentials were rotated but the application still holds the old ones.
- The database was deleted or detached from the project.

### Docker Compose

- The database container has crashed or is still starting up (race condition on boot).
- The service name or network alias has changed — Django's `HOST` setting points to the wrong container.
- The port mapping is misconfigured; the container is listening on a different port externally.
- The data volume is corrupt or has been recreated, causing authentication failures.
- DNS within the Compose network is flaky when containers restart.

### Generic

- A transient network partition interrupted the handshake between the app and the database.
- The database server is down for maintenance or has run out of disk space.
- TLS/SSL configuration mismatch between the client and the server.
- The database user no longer has `CONNECT` privilege or has been dropped.
- A firewall rule or security group is blocking the connection on the database port.
