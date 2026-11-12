# Runbook: slack-support-bot

How to operate and troubleshoot the bot. For setup, see the [README](../README.md).

## At a glance

| Item | Where |
|---|---|
| Process | `python -m support_bot` (container service `bot`) |
| Connection | Slack Socket Mode (outbound WebSocket, no public URL) |
| State | `DATA_DIR` (Docker volume `bot-data`): `chroma/`, `support_bot.db`, `heartbeat` |
| Logs | JSON lines on stdout (`docker compose logs -f bot`) |
| Health | `python -m support_bot.health` (Docker `HEALTHCHECK`) |
| Metrics | Send `status` to the bot, or query the `requests` table |

## Routine operations

### Start, stop, restart

```bash
docker compose up -d --build bot
docker compose logs -f bot
docker compose restart bot
docker compose down          # keeps the data volume
```

### Update the knowledge base

1. Edit or add Markdown files under `knowledge_base/` (one H1 title, sections as H2/H3).
2. Rebuild the image (the knowledge base is copied into it) and run ingestion:

   ```bash
   docker compose build
   docker compose run --rm ingest
   ```

   Ingestion is idempotent: unchanged chunks are skipped, changed chunks are re-embedded, and removed chunks are deleted. The bot does not need a restart.

### Change the embedding model or dimension

The index records the embedding model and dimension. After you change `GEMINI_EMBEDDING_MODEL` or `GEMINI_EMBEDDING_DIM`, the bot refuses to start (`startup_failed` with "Index was built with embedding model/dim ...") until you rebuild:

```bash
docker compose run --rm ingest python -m support_bot.ingest --rebuild
```

Then run the evals again and re-check `RETRIEVAL_MIN_SCORE`.

### Back up and inspect data

```bash
docker compose cp bot:/app/data ./backup-data      # copy the whole data directory
sqlite3 backup-data/support_bot.db "SELECT id, title, priority, status, datetime(created_at, 'unixepoch') FROM tickets ORDER BY id DESC LIMIT 20;"
```

Useful queries:

```sql
-- outcomes and latency over the last 24 hours
SELECT outcome, COUNT(*), ROUND(AVG(latency_ms)) FROM requests
WHERE created_at >= strftime('%s','now') - 86400 GROUP BY outcome;

-- answers rated thumbs down, with what was retrieved
SELECT r.id, r.outcome, r.retrieved FROM feedback f JOIN requests r ON r.id = f.request_id
WHERE f.rating = 'down' ORDER BY f.created_at DESC LIMIT 20;

-- recent errors
SELECT id, datetime(created_at, 'unixepoch'), error FROM requests
WHERE outcome = 'error' ORDER BY created_at DESC LIMIT 20;
```

## Troubleshooting

### Container is `unhealthy`

The heartbeat file is older than `HEARTBEAT_MAX_AGE_SECONDS` (90 s by default). It is written only while the Socket Mode connection is up.

1. `docker compose logs --tail 200 bot`. Look for `socket_mode_disconnected`, `startup_failed` or tracebacks.
2. `startup_failed` with `SLACK_*_TOKEN is not set` or `invalid_auth`: check `.env` and that the app is installed in the workspace. Reinstalling the app rotates the bot token.
3. Repeated `socket_mode_disconnected`: check outbound connectivity to `wss-primary.slack.com` (proxy or firewall). The SDK reconnects automatically.
4. `docker compose restart bot` as a last resort.

### The bot does not reply

- **In a channel**: the bot must be invited (`/invite @Support Bot`) and mentioned.
- **In DMs**: the app manifest must enable the Messages tab and subscribe to `message.im`.
- Look for `duplicate_event_skipped`: the message was already processed (Slack retry, or the same message arriving as both `app_mention` and `message.im`).
- Messages from bots, edits and other message subtypes are ignored on purpose.

### Replies say "trouble reaching the AI service"

The Gemini call failed after all retries. Check the `request_completed` logs: their `error` field holds the status code.

| Status | Meaning | Action |
|---|---|---|
| 429 | Quota or rate limit | Wait, or raise the quota in Google AI Studio |
| 400 / 404 | Bad request or unknown model | Check `GEMINI_MODEL` against the current model list |
| 401 / 403 | Invalid or restricted API key | Rotate `GEMINI_API_KEY` |
| 5xx / timeout | Provider issue | Retried automatically; tune `GEMINI_TIMEOUT_SECONDS` / `GEMINI_MAX_ATTEMPTS` |

### Too many "I don't know" answers

- Run `status`: if *Indexed chunks* is 0, run ingestion.
- Check `retrieved` scores in the logs. If relevant chunks score just below `RETRIEVAL_MIN_SCORE`, lower it and re-run the evals (`uv run python -m evals.run`) to check the refusal rates.
- Add or improve the knowledge base article for the missing topic.

### Wrong or unhelpful answers

Find the request by `request_id` in the logs or in the thumbs-down query above. Check which chunks were retrieved. Usually the fix is in the knowledge base (missing or ambiguous text). Add the question to `evals/golden.jsonl` so it is covered next time.

### Ticket buttons say "expired" or "already handled"

Drafts expire after `PENDING_ACTION_TTL_SECONDS` (15 minutes by default) and can be confirmed once. Ask the bot again to create a new draft. Only the person who asked can confirm a draft.

## Security notes

- Secrets live only in `.env` or the orchestrator's secret store, never in the image or the repo.
- User ids appear in logs and metrics only as salted HMACs (`USER_ID_HASH_SALT`). Tickets store the raw Slack user id, so the Service Desk can contact the requester.
- Document text and user messages are treated as untrusted data in the prompts. Answers without valid citations are never shown.
- To rotate Slack tokens, regenerate them in the app settings, update `.env` and run `docker compose up -d bot`.
