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
    ]
}
```

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

## VM Monitor Integration

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

## License

MIT
