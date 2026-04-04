# TicketBlitz

## Docker Startup

Start the stack with explicit env-file interpolation so RabbitMQ bootstrap credentials and
service URLs resolve from the same source:

```bash
docker compose --env-file .env.local up -d --build
```

## RabbitMQ Credential Sanity Check

If orchestration calls fail with `ACCESS_REFUSED`, validate broker credentials directly:

```bash
docker exec ticketblitz-rabbitmq rabbitmqctl authenticate_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD"
```

The command should return `Success`.

## Flash Sale Manual Test Troubleshooting

If flash-sale manual tests start failing right after service path or Kong route changes,
recreate Kong and the orchestrators so runtime state matches the latest files:

```bash
docker compose --env-file .env.local up -d --build --force-recreate flash-sale-orchestrator pricing-orchestrator kong
```

Then verify that Kong has the expected routes loaded:

```bash
curl http://localhost:8001/routes
```

On PowerShell, prefer `Invoke-RestMethod` for JSON POST requests. Quoting issues with
`curl.exe -d` can produce `{"error":"Request body must be a JSON object"}` even when
the endpoint is healthy.