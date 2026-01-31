# Message Relay

A lightweight Telegram notification gateway for VM Monitor.

## Why?

- **Centralized bot token** - Not exposed in every VM Monitor config
- **Template-only messaging** - Prevents arbitrary message abuse
- **Multi-tenant** - Each dashboard gets its own API key
- **Audit logging** - All messages logged centrally

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure
cp instance/config.json.example instance/config.json
# Edit instance/config.json with your bot token and API keys

# Run
python app.py
```

## Configuration

### `instance/config.json`
```json
{
    "telegram_bot_token": "1234567890:ABC...",
    "api_keys": [
        "your-api-key-1",
        "your-api-key-2"
    ],
    "authorized_chats": [
        "123456789",
        "987654321"
    ]
}
```

**Finding your Chat ID:**
1. Start the bot (even without auth configured temporarily)
2. Send any message to your bot (e.g., `/start`)
3. Check the logs - you'll see: `Bot command from <YOUR_CHAT_ID> (YourName): /start`
4. Add that Chat ID to `authorized_chats`
5. Restart the bot

> **Security Note:** Only users whose Chat IDs are in `authorized_chats` can use bot commands. If this list is empty or missing, **all commands will be rejected**.

### `templates.json` (optional)
Add custom templates:
```json
{
    "my_template": "Hello {name}!"
}
```

## API

### `POST /send`
Send a single message.

```bash
curl -X POST http://localhost:5001/send \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "vm_alert",
    "chat_id": "8243412741",
    "variables": {
        "hostname": "web-server-01",
        "resource": "CPU",
        "value": "95"
    }
}'
```

### `POST /send/batch`
Send to multiple recipients.

```bash
curl -X POST http://localhost:5001/send/batch \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "summary",
    "chat_ids": ["8243412741", "987654321"],
    "variables": {
        "count": "3",
        "details": "web-01, db-02, api-03"
    }
}'
```

### `GET /templates`
List available templates.

```bash
curl http://localhost:5001/templates -H "X-API-Key: your-api-key"
```

## Built-in Templates

| Template | Variables | Example |
|----------|-----------|---------|
| `vm_alert` | hostname, resource, value, dashboard_url | 🔴 *web-01* - CPU at 95% |
| `vm_warning` | hostname, resource, value | ⚠️ *web-01* - RAM at 82% |
| `summary` | count, details, dashboard_url | 📊 3 VMs need attention |
| `vm_offline` | hostname, last_seen | 🔌 *web-01* is offline |
| `vm_recovered` | hostname, resource, value | ✅ *web-01* - CPU recovered |
| `test` | (none) | ✅ Message relay is working! |
| `custom` | message | (any text) |

## Telegram Bot Commands

The bot supports interactive commands for querying VM status directly from Telegram:

| Command | Description |
|---------|-------------|
| `/start` or `/help` | Show available commands |
| `/summary` | Quick overview of all VMs (online/offline counts, alerts) |
| `/alerts` | Show only VMs with issues (offline or high resource usage) |
| `/detailed` | Full list of all VMs with CPU/RAM/Disk metrics |
| `/vm <hostname>` | Detailed stats for a specific VM |

### Bot Command Authorization

**🔒 Security:** Bot commands use a **separate authorization mechanism** from API endpoints.

- **API endpoints** (`/send`, `/send/batch`) require an API key via `X-API-Key` header
- **Bot commands** (like `/summary`, `/alerts`) require the user's Telegram Chat ID to be in the `authorized_chats` list

**How it works:**
1. When a user sends a command to the bot, the webhook receives their Chat ID
2. The bot checks if that Chat ID exists in `authorized_chats` in `config.json`
3. If **not authorized** → User receives: "⛔ You are not authorized to use this bot."
4. If **authorized** → Command is executed and results are sent

**Fail-safe behavior:**
- If `authorized_chats` is **empty** or **missing** → **ALL users are denied** (secure by default)
- If `authorized_chats` contains IDs → **Only those users** can use commands
- Unauthorized attempts are logged with: `Unauthorized command attempt from <chat_id> (<username>)`

### Setting Up Bot Commands

1. **Configure webhook** (required for bot commands):
   ```bash
   curl -X POST http://localhost:5001/webhook/setup \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"webhook_url": "https://your-domain.com/webhook"}'
   ```

2. **Configure VM Monitor URL** in `instance/config.json`:
   ```json
   {
       "telegram_bot_token": "...",
       "api_keys": ["..."],
       "authorized_chats": ["123456789"],
       "vm_monitor_url": "http://your-vm-monitor:5000"
   }
   ```

3. **Test the bot** by sending `/summary` in Telegram

## VM Monitor Integration

### For Automated Alerts

In your VM Monitor `instance/sms_config.json`:

```json
{
    "provider": "relay",
    "relay": {
        "url": "http://relay-server:5001",
        "api_key": "your-api-key",
        "chat_ids": ["8243412741"]
    }
}
```

### For Bot Commands

No configuration needed in VM Monitor! The relay service connects to VM Monitor's API automatically using the `vm_monitor_url` in `instance/config.json`.

## License

MIT
