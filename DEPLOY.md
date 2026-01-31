# Deployment & Update Guide

## Initial Deployment

### 1. Clone the repository
```bash
cd /path/to/your/apps
git clone https://github.com/aydinguven/message-relay.git
cd message-relay
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the application
```bash
# Copy example config
cp instance/config.json.example instance/config.json

# Edit with your settings
nano instance/config.json
```

Required configuration:
```json
{
    "telegram_bot_token": "YOUR_BOT_TOKEN",
    "api_keys": ["your-secure-api-key"],
    "authorized_chats": ["YOUR_TELEGRAM_CHAT_ID"],
    "vm_monitor_url": "http://your-vm-monitor:5000"
}
```

### 4. Set up as a systemd service (Linux)

Create `/etc/systemd/system/message-relay.service`:
```ini
[Unit]
Description=Message Relay Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/message-relay
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable message-relay
sudo systemctl start message-relay
sudo systemctl status message-relay
```

### 5. Configure webhook
```bash
curl -X POST http://localhost:5001/webhook/setup \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-domain.com/webhook"}'
```

---

## Updating Your Deployed Application

### Quick Update (One-liner)
```bash
cd /path/to/message-relay && git pull && sudo systemctl restart message-relay
```

### Step-by-Step Update

1. **Navigate to the app directory**
   ```bash
   cd /path/to/message-relay
   ```

2. **Backup your current config (optional but recommended)**
   ```bash
   cp instance/config.json instance/config.json.backup
   ```

3. **Pull the latest changes**
   ```bash
   git pull origin main
   ```

4. **Check if dependencies changed**
   ```bash
   pip install -r requirements.txt --upgrade
   ```

5. **Verify your config is still valid**
   ```bash
   cat instance/config.json
   # Ensure all required fields are present
   ```

6. **Restart the service**
   
   **If using systemd:**
   ```bash
   sudo systemctl restart message-relay
   sudo systemctl status message-relay
   ```
   
   **If running manually:**
   ```bash
   # Find and kill the process
   pkill -f "python.*app.py"
   
   # Start it again
   nohup python app.py > logs/app.log 2>&1 &
   ```
   
   **If using screen/tmux:**
   ```bash
   # Attach to the session
   screen -r message-relay  # or: tmux attach -t message-relay
   
   # Stop the app (Ctrl+C)
   # Pull changes (git pull)
   # Start again (python app.py)
   ```

7. **Verify the update**
   ```bash
   # Check logs
   sudo journalctl -u message-relay -f
   
   # Or if logging to file
   tail -f logs/app.log
   
   # Test the API
   curl http://localhost:5001/
   ```

---

## Troubleshooting

### Service won't start after update
```bash
# Check logs
sudo journalctl -u message-relay -n 50

# Check if port is already in use
sudo lsof -i :5001

# Verify Python dependencies
pip list | grep -E "flask|requests"
```

### Config file issues
```bash
# Validate JSON syntax
python -c "import json; json.load(open('instance/config.json'))"

# Compare with example
diff instance/config.json instance/config.json.example
```

### Webhook not working after update
```bash
# Check current webhook status
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo

# Re-configure webhook
curl -X POST http://localhost:5001/webhook/setup \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-domain.com/webhook"}'
```

---

## Rolling Back

If the update causes issues:

```bash
# View recent commits
git log --oneline -5

# Rollback to previous version
git checkout <previous-commit-hash>

# Or rollback one commit
git reset --hard HEAD~1

# Restart service
sudo systemctl restart message-relay
```

---

## Docker Deployment (Alternative)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t message-relay .
docker run -d \
  -p 5001:5001 \
  -v $(pwd)/instance:/app/instance \
  --name message-relay \
  --restart unless-stopped \
  message-relay
```

Update with Docker:
```bash
cd /path/to/message-relay
git pull
docker stop message-relay
docker rm message-relay
docker build -t message-relay .
docker run -d -p 5001:5001 -v $(pwd)/instance:/app/instance --name message-relay --restart unless-stopped message-relay
```

---

## Monitoring

Check service health:
```bash
# Service status
sudo systemctl status message-relay

# View logs
sudo journalctl -u message-relay -f

# Check if responding
curl http://localhost:5001/

# Monitor resource usage
top -p $(pgrep -f "python.*app.py")
```
