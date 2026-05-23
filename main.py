from flask import Flask, request, jsonify
import os
import datetime
import requests as http_requests

app = Flask(__name__)

# In-memory rate limiter: date_str -> ip -> count
proxy_usage = {}

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-License-Key, X-App-Id"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/")
def root():
    return jsonify({"status": "ok", "service": "SocialIntent API Proxy"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/api/gemini-proxy", methods=["OPTIONS"])
def preflight():
    return jsonify({}), 200

@app.route("/api/gemini-proxy", methods=["POST"])
def gemini_proxy():
    data = request.get_json(force=True) or {}

    # 1. License check
    license_key = request.headers.get("X-License-Key", "")
    is_premium = license_key.strip().upper().startswith("LS-") and len(license_key.strip()) >= 10

    # 2. Client IP
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "127.0.0.1"

    # 3. Rate limit (3 req/day for free tier)
    if not is_premium:
        today = datetime.date.today().isoformat()
        for d in list(proxy_usage.keys()):
            if d != today:
                proxy_usage.pop(d, None)
        proxy_usage.setdefault(today, {})
        count = proxy_usage[today].get(ip, 0)
        if count >= 3:
            return jsonify({"error": "Rate limit exceeded"}), 429
        proxy_usage[today][ip] = count + 1

    # 4. Forward to Gemini
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    model = data.get("model", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    try:
        res = http_requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"contents": data.get("contents", [])},
            timeout=30,
        )
        return jsonify(res.json()), res.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
