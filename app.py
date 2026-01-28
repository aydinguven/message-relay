"""
Message Relay Service - Centralized Telegram notification gateway.

A lightweight Flask service that:
- Holds the Telegram bot token centrally
- Authenticates clients via API key
- Only sends predefined message templates

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


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "service": "message-relay",
        "status": "ok",
        "version": "1.0.0"
    })


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
            "api_keys": ["changeme"]
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default config at {CONFIG_FILE}")
    
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting Message Relay on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
