# ADR 0001: Use Slack Socket Mode instead of the Events API over HTTP

- Status: Accepted
- Date: 2026-11-12

## Context

The bot must receive `app_mention` and `message.im` events and Block Kit button clicks. Slack can deliver them in two ways:

1. **Events API over HTTP**: Slack sends HTTPS requests to a public URL. This needs a reachable endpoint, TLS, request signature checks, and usually a load balancer or tunnel.
2. **Socket Mode**: the app opens an outbound WebSocket to Slack with an app-level token (`xapp-...`), and events arrive over that connection.

The bot runs as one container with `docker compose` and has no public ingress. It is an internal tool with modest traffic.

## Decision

Use Socket Mode, through slack-bolt's `SocketModeHandler`.

## Consequences

- No public URL, TLS certificate, or ingress configuration is needed. The container only makes outbound connections, which reduces the attack surface.
- An extra secret is required: the app-level token `SLACK_APP_TOKEN` with the `connections:write` scope.
- No HTTP health endpoint exists. The Docker `HEALTHCHECK` instead reads a heartbeat file that is written only while the WebSocket is connected.
- Socket Mode apps cannot be published to the Slack Marketplace, and Slack recommends HTTP for large-scale apps. Neither applies to this internal bot.
- Scaling out to several replicas would deliver each event to only one connection. The bot already de-duplicates events in SQLite, but state is local to one instance, so horizontal scaling would need a shared database (see the roadmap).
