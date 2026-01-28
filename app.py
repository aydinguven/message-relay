"""
Message Relay Service - Centralized Telegram notification gateway.

A lightweight Flask service that:
- Holds the Telegram bot token centrally
- Authenticates clients via API key
- Only sends predefined message templates
- Handles Telegram bot commands (/summary, /detailed)

Run: python app.py
"""

import json
import logging
import os
from datetime import datetime
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Config paths
CONFIG_DIR = Path(__file__).parent / "instance"
CONFIG_FILE = CONFIG_DIR / "config.json"
TEMPLATES_FILE = Path(__file__).parent / "templates.json"

# Default templates
DEFAULT_TEMPLATES = {
    "vm_alert": "🔴 *{hostname}* - {resource} at {value}%",
    "vm_warning": "⚠️ *{hostname}* - {resource} at {value}%",
    "summary": "📊 *Alert Summary*\n{count} VMs need attention",
    "test": "✅ Message relay is working! Sent at {timestamp}",
    "custom": "{message}"
}


def get_authorized_chats():
    """Get list of chat IDs authorized to use bot commands."""
    config = load_config()
    return config.get("authorized_chats", [])


def load_config():
    """Load config from file."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}


def load_templates():
    """Load message templates."""
    if not TEMPLATES_FILE.exists():
        return DEFAULT_TEMPLATES
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            templates = json.load(f)
            return {**DEFAULT_TEMPLATES, **templates}
    except Exception as e:
        logger.error(f"Error loading templates: {e}")
        return DEFAULT_TEMPLATES


def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        config = load_config()
        api_keys = config.get("api_keys", [])
        
        # Get API key from header or query param
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401
        
        if api_key not in api_keys:
            logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
            return jsonify({"error": "Invalid API key"}), 403
        
        return f(*args, **kwargs)
    return decorated


def send_telegram_message(chat_id: str, text: str) -> dict:
    """Send message via Telegram Bot API."""
    config = load_config()
    bot_token = config.get("telegram_bot_token", "")
    
    if not bot_token:
        return {"ok": False, "error": "Bot token not configured"}
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    try:
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=30)
        
        result = response.json()
        if result.get("ok"):
            logger.info(f"Telegram message sent to {chat_id}")
        else:
            logger.error(f"Telegram error: {result.get('description')}")
        return result
    except Exception as e:
        logger.error(f"Telegram request error: {e}")
        return {"ok": False, "error": str(e)}


def fetch_vm_summary():
    """Fetch VM summary from VM Monitor API."""
    config = load_config()
    vm_monitor_url = config.get("vm_monitor_url", "http://localhost:5000")
    
    try:
        response = requests.get(f"{vm_monitor_url}/api/vms", timeout=10)
        if response.status_code != 200:
             return f"⚠️ API Error: {response.status_code} - {response.text}"
             
        vms = response.json()
        
        if isinstance(vms, dict) and "vms" in vms:
            vms = vms["vms"]
            
        if not isinstance(vms, list):
             return f"⚠️ Unexpected API response type: {type(vms)}"
        
        # Count online/offline
        online = sum(1 for vm in vms if vm.get("status") == "online")
        offline = sum(1 for vm in vms if vm.get("status") == "offline")
        
        # Count alerts/warnings
        alerts = 0
        warnings = 0
        for vm in vms:
            cpu = vm.get("cpu_avg", 0)
            ram = vm.get("ram_percent", 0)
            if cpu >= 90 or ram >= 90:
                alerts += 1
            elif cpu >= 80 or ram >= 80:
                warnings += 1
        
        # Build message
        status_emoji = "🟢" if alerts == 0 and warnings == 0 else ("🔴" if alerts > 0 else "🟡")
        lines = [
            f"{status_emoji} *VM Monitor Summary*",
            f"📊 {online} online, {offline} offline"
        ]
        if alerts > 0:
            lines.append(f"🚨 {alerts} critical alerts")
        if warnings > 0:
            lines.append(f"⚠️ {warnings} warnings")
        if alerts == 0 and warnings == 0:
            lines.append("✅ All systems healthy")
        
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error fetching VM summary: {e}")
        return f"❌ Error fetching VMs: {e}"


def fetch_vm_alerts():
    """Fetch only VMs with alerts/warnings."""
    config = load_config()
    vm_monitor_url = config.get("vm_monitor_url", "http://localhost:5000")
    
    try:
        response = requests.get(f"{vm_monitor_url}/api/vms", timeout=10)
        if response.status_code != 200:
             return f"⚠️ API Error: {response.status_code}"
             
        vms = response.json()
        if isinstance(vms, dict) and "vms" in vms:
            vms = vms["vms"]
            
        if not isinstance(vms, list):
             return f"⚠️ API returned {type(vms)}, expected list"
        
        issues = []
        for vm in vms:
            cpu = vm.get("cpu_avg", 0)
            ram = vm.get("ram_percent", 0)
            disk_str = vm.get("disk_usage", "0%")
            is_online = vm.get("online", False)
            status = "online" if is_online else "offline"
            last_seen = vm.get("last_seen", "").replace("T", " ")[:16]

            # Parse disk
            try:
                disk = float(disk_str.strip('%'))
            except:
                disk = 0

            if not is_online:
                issues.append(f"🔴 *{vm.get('hostname')}* is OFFLINE\n    └ _Last seen: {last_seen}_")
            elif cpu >= 80 or ram >= 80 or disk >= 90:
                reason = []
                if cpu >= 80: reason.append(f"CPU {cpu:.0f}%")
                if ram >= 80: reason.append(f"RAM {ram:.0f}%")
                if disk >= 90: reason.append(f"Disk {disk:.0f}%")
                
                emoji = "🔴" if (cpu>=90 or ram>=90 or disk>=95) else "⚠️"
                issues.append(f"{emoji} *{vm.get('hostname')}*: {', '.join(reason)}")

        if not issues:
            return "✅ *System Healthy*\nNo active alerts found."
            
        return "🚨 *Active Alerts*\n\n" + "\n\n".join(issues)

    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        return f"❌ Error: {e}"


def fetch_vm_single(hostname_query):
    """Fetch details for a specific VM."""
    config = load_config()
    vm_monitor_url = config.get("vm_monitor_url", "http://localhost:5000")
    
    try:
        response = requests.get(f"{vm_monitor_url}/api/vms", timeout=10)
        if response.status_code != 200:
             return f"⚠️ API Error: {response.status_code}"

        vms = response.json()
        if isinstance(vms, dict) and "vms" in vms:
            vms = vms["vms"]
            
        if not isinstance(vms, list):
             return f"⚠️ API returned {type(vms)}, expected list"
            
        matches = [v for v in vms if hostname_query.lower() in v.get("hostname", "").lower()]
        
        if not matches:
            return f"❓ No VM found containing `{hostname_query}`"
        
        if len(matches) > 1:
            return f"⚠️ Found {len(matches)} matches:\n" + \
                   "\n".join([f"- `{m.get('hostname')}`" for m in matches[:5]])
        
        vm = matches[0]
        is_online = vm.get("online", False)
        emoji = "🟢" if is_online else "🔴"
        last_seen = vm.get("last_seen", "").replace("T", " ")
        
        # Helper for progress bar
        def bar(percent):
            filled = int(percent / 10)
            return "▰" * filled + "▱" * (10 - filled)

        return (
            f"{emoji} *{vm.get('hostname')}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💻 *OS*: `{vm.get('os_name', 'Unknown')}`\n"
            f"📟 *Agent*: `v{vm.get('agent_version', '?')}`\n"
            f"🔄 *Updates*: `{vm.get('pending_updates', 0)}` pending\n\n"
            f"*Resources*\n"
            f"CPU:  `{vm.get('cpu_avg', 0):>5.1f}%` {bar(vm.get('cpu_avg', 0))}\n"
            f"RAM:  `{vm.get('ram_percent', 0):>5.1f}%` {bar(vm.get('ram_percent', 0))}\n"
            f"*Disk Usage*:\n"
            + "\n".join([f"  • `{k}`: `{v}`" for k, v in (vm.get('disk_usage') or {}).items()]) + "\n\n"
            f"🕒 *Last Seen*: `{last_seen}`"
        )

    except Exception as e:
        logger.error(f"Error fetching VM: {e}")
        return f"❌ Error: {e}"


def fetch_vm_detailed():
    """Fetch detailed VM list."""
    config = load_config()
    vm_monitor_url = config.get("vm_monitor_url", "http://localhost:5000")
    
    try:
        response = requests.get(f"{vm_monitor_url}/api/vms", timeout=10)
        if response.status_code != 200:
             return f"⚠️ API Error: {response.status_code}"

        vms = response.json()
        if isinstance(vms, dict) and "vms" in vms:
            vms = vms["vms"]
            
        if not isinstance(vms, list):
             return f"⚠️ API returned {type(vms)}, expected list"
        
        # Header
        table = f"{'Host':<14} {'CPU':<4} {'RAM':<4} {'Disk':<4}\n"
        table += "-" * 30 + "\n"
        
        vms_sorted = sorted(vms, key=lambda v: (
            v.get("status") == "online",
            -v.get("cpu_avg", 0)
        ))
        
        for vm in vms_sorted[:20]:
            is_online = vm.get("online", False)
            # Truncate hostname to 14 chars
            hostname = vm.get("hostname", "?")[:13]
            
            if is_online:
                cpu = f"{vm.get('cpu_avg', 0):.0f}%"
                ram = f"{vm.get('ram_percent', 0):.0f}%"
                
                # Handle disk parsing (it's a dict like {'/': '20%'})
                disk_data = vm.get("disk_usage")
                disk_val = 0
                if isinstance(disk_data, dict):
                    # Find max usage across mounts
                    try:
                        disk_val = max([float(v.strip('%')) for v in disk_data.values() if v.strip('%').replace('.', '', 1).isdigit()], default=0)
                    except Exception:
                        disk_val = 0
                elif isinstance(disk_data, (int, float)):
                    disk_val = disk_data
                elif isinstance(disk_data, str):
                    # Fallback for string "45%"
                    try:
                        disk_val = float(disk_data.strip('%'))
                    except:
                        disk_val = 0
                        
                disk = f"{disk_val:.0f}%"
                
                table += f"{hostname:<14} {cpu:<4} {ram:<4} {disk:<4}\n"
            else:
                table += f"{hostname:<14} 🔴 OFFLINE\n"
        
        if len(vms) > 20:
            table += f"\n...and {len(vms) - 20} more"
        
        return f"📋 *Fleet Status*\n```\n{table}```"

    except Exception as e:
        logger.error(f"Error fetching VM details: {e}")
        return f"❌ Error: {e}"


def handle_bot_command(chat_id: str, command: str, user_name: str = ""):
    """Handle incoming bot commands."""
    # Check authorization
    authorized = get_authorized_chats()
    if authorized and str(chat_id) not in [str(c) for c in authorized]:
        logger.warning(f"Unauthorized command attempt from {chat_id}")
        send_telegram_message(chat_id, "⛔ You are not authorized to use this bot.")
        return
    
    full_command = command.lower().strip()
    parts = full_command.split()
    cmd = parts[0].split('@')[0]  # Handle /command@botname
    args = parts[1:] if len(parts) > 1 else []
    
    if cmd == "/start":
        msg = (
            "👋 *VM Monitor Bot*\n\n"
            "Available commands:\n"
            "/summary - Quick overview\n"
            "/alerts - Active issues only\n"
            "/detailed - Full list with Disk usage\n"
            "/vm <name> - Specific VM details\n"
            "/help - Show this message"
        )
        send_telegram_message(chat_id, msg)
    
    elif cmd == "/summary":
        msg = fetch_vm_summary()
        send_telegram_message(chat_id, msg)

    elif cmd == "/alerts":
        msg = fetch_vm_alerts()
        send_telegram_message(chat_id, msg)
    
    elif cmd in ["/detailed", "/detail", "/list"]:
        msg = fetch_vm_detailed()
        send_telegram_message(chat_id, msg)
        
    elif cmd == "/vm":
        if not args:
            send_telegram_message(chat_id, "ℹ️ Usage: `/vm <hostname>`")
        else:
            msg = fetch_vm_single(args[0])
            send_telegram_message(chat_id, msg)
    
    elif cmd == "/help":
        msg = (
            "📖 *Help*\n\n"
            "/summary - Quick status overview\n"
            "/alerts - Show OFFLINE or High Resource VMs\n"
            "/detailed - List all VMs (CPU/RAM/Disk)\n"
            "/vm <name> - Details for specific VM\n"
        )
        send_telegram_message(chat_id, msg)
    
    else:
        send_telegram_message(chat_id, "❓ Unknown command. Try /help")


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "service": "message-relay",
        "status": "ok",
        "version": "1.1.0"
    })


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram updates (webhook mode)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"ok": True})
    
    # Extract message info
    message = data.get("message", {})
    text = message.get("text", "")
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user = message.get("from", {})
    user_name = user.get("first_name", "")
    
    if not chat_id or not text:
        return jsonify({"ok": True})
    
    # Only handle commands (messages starting with /)
    if text.startswith("/"):
        # Log the raw text for debugging, pass full text to handler
        logger.info(f"Bot command from {chat_id} ({user_name}): {text}")
        handle_bot_command(str(chat_id), text, user_name)
    
    return jsonify({"ok": True})


@app.route("/webhook/setup", methods=["POST"])
@require_api_key
def setup_webhook():
    """Set up Telegram webhook."""
    data = request.get_json() or {}
    webhook_url = data.get("webhook_url")
    
    if not webhook_url:
        return jsonify({"error": "webhook_url is required"}), 400
    
    config = load_config()
    bot_token = config.get("telegram_bot_token", "")
    
    if not bot_token:
        return jsonify({"error": "Bot token not configured"}), 400
    
    # Set webhook
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    try:
        response = requests.post(url, json={"url": webhook_url}, timeout=30)
        result = response.json()
        
        if result.get("ok"):
            logger.info(f"Webhook set to {webhook_url}")
            return jsonify({"success": True, "message": "Webhook configured"})
        else:
            return jsonify({"error": result.get("description")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/webhook/delete", methods=["POST"])
@require_api_key  
def delete_webhook():
    """Delete Telegram webhook (switch back to polling)."""
    config = load_config()
    bot_token = config.get("telegram_bot_token", "")
    
    if not bot_token:
        return jsonify({"error": "Bot token not configured"}), 400
    
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    try:
        response = requests.post(url, timeout=30)
        result = response.json()
        
        if result.get("ok"):
            logger.info("Webhook deleted")
            return jsonify({"success": True, "message": "Webhook deleted"})
        else:
            return jsonify({"error": result.get("description")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/templates")
@require_api_key
def list_templates():
    """List available message templates."""
    templates = load_templates()
    return jsonify({
        "templates": list(templates.keys()),
        "details": templates
    })


@app.route("/send", methods=["POST"])
@require_api_key
def send_message():
    """
    Send a message using a predefined template.
    
    Request body:
    {
        "template": "vm_alert",
        "chat_id": "8243412741",
        "variables": {
            "hostname": "web-server-01",
            "resource": "CPU",
            "value": "95"
        }
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Request body required"}), 400
    
    template_name = data.get("template")
    chat_id = data.get("chat_id")
    variables = data.get("variables", {})
    
    if not template_name:
        return jsonify({"error": "template is required"}), 400
    
    if not chat_id:
        return jsonify({"error": "chat_id is required"}), 400
    
    # Load templates
    templates = load_templates()
    
    if template_name not in templates:
        return jsonify({
            "error": f"Unknown template: {template_name}",
            "available": list(templates.keys())
        }), 400
    
    # Format message
    template = templates[template_name]
    
    # Add timestamp if not provided
    if "timestamp" not in variables:
        variables["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        message = template.format(**variables)
    except KeyError as e:
        return jsonify({
            "error": f"Missing variable: {e}",
            "template": template,
            "provided": list(variables.keys())
        }), 400
    
    # Send via Telegram
    result = send_telegram_message(chat_id, message)
    
    if result.get("ok"):
        return jsonify({
            "success": True,
            "message": "Message sent",
            "chat_id": chat_id,
            "template": template_name
        })
    else:
        return jsonify({
            "success": False,
            "error": result.get("description") or result.get("error", "Unknown error")
        }), 500


@app.route("/send/batch", methods=["POST"])
@require_api_key
def send_batch():
    """
    Send messages to multiple chat IDs.
    
    Request body:
    {
        "template": "vm_alert",
        "chat_ids": ["8243412741", "987654321"],
        "variables": {...}
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Request body required"}), 400
    
    template_name = data.get("template")
    chat_ids = data.get("chat_ids", [])
    variables = data.get("variables", {})
    
    if not template_name:
        return jsonify({"error": "template is required"}), 400
    
    if not chat_ids:
        return jsonify({"error": "chat_ids is required"}), 400
    
    # Load templates
    templates = load_templates()
    
    if template_name not in templates:
        return jsonify({
            "error": f"Unknown template: {template_name}",
            "available": list(templates.keys())
        }), 400
    
    # Format message
    template = templates[template_name]
    if "timestamp" not in variables:
        variables["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        message = template.format(**variables)
    except KeyError as e:
        return jsonify({"error": f"Missing variable: {e}"}), 400
    
    # Send to all
    results = []
    for chat_id in chat_ids:
        result = send_telegram_message(str(chat_id), message)
        results.append({
            "chat_id": chat_id,
            "ok": result.get("ok", False)
        })
    
    success_count = sum(1 for r in results if r["ok"])
    
    return jsonify({
        "success": success_count > 0,
        "sent": success_count,
        "total": len(chat_ids),
        "results": results
    })


if __name__ == "__main__":
    # Ensure instance directory exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create default config if not exists
    if not CONFIG_FILE.exists():
        default_config = {
            "telegram_bot_token": "",
            "api_keys": ["changeme"],
            "vm_monitor_url": "http://localhost:5000",
            "authorized_chats": []
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default config at {CONFIG_FILE}")
    
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting Message Relay on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
