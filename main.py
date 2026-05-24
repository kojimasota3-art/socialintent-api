# -*- coding: utf-8 -*-
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file if it exists

from flask import Flask, request, jsonify
import os
import datetime
import random
import string
import requests as http_requests

import database
import stripe_integration

app = Flask(__name__)

# Initialize the database on startup
database.init_db()

# In-memory rate limiter: date_str -> ip -> count
proxy_usage = {}

import hmac
import hashlib

LICENSE_SALT = os.environ.get("LICENSE_SIGNING_SALT", "aoi_software_studio_secret_salt")

def generate_license_key():
    """Generate a signed license key in the format LS-PREMIUM-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    
    # Calculate signature on the random part
    h = hmac.new(LICENSE_SALT.encode("utf-8"), part1.encode("utf-8"), hashlib.sha256)
    sig = h.hexdigest().upper()
    part2 = sig[:4]
    
    return f"LS-PREMIUM-{part1}-{part2}"

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

# Rate limiters for security protection (Credit Master & brute force validation prevention)
checkout_creation_log = {}

def is_checkout_rate_limited(ip, max_requests=5, window_seconds=60):
    """
    Sliding window rate limiter to prevent bot abuse (Credit Master / card validation spamming).
    """
    now = datetime.datetime.now().timestamp()
    timestamps = checkout_creation_log.get(ip, [])
    # Filter out timestamps older than the window
    timestamps = [t for t in timestamps if now - t < window_seconds]
    checkout_creation_log[ip] = timestamps
    
    if len(timestamps) >= max_requests:
        return True
        
    timestamps.append(now)
    return False

# 1. API to create a Stripe Checkout Session
@app.route("/api/checkout-session", methods=["POST", "OPTIONS"])
def create_checkout():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    # 1. Security Check: Client IP check and rate limiting to block Credit Master script attacks
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "127.0.0.1"
    if is_checkout_rate_limited(ip, max_requests=5, window_seconds=60):
        print(f"Security Shield: IP {ip} rate limited on checkout session creation.")
        return jsonify({"error": "Too many requests. Please try again later."}), 429
        
    data = request.get_json(force=True) or {}
    email = data.get("email", "sota.kojima@empire.com")
    origin = data.get("origin")
    
    if not origin:
        # Fallback to referrer or host header if not provided
        origin = request.headers.get("Origin") or request.referrer or "http://localhost:10000"
        
    try:
        session_info = stripe_integration.create_checkout_session(email, origin)
        return jsonify(session_info)
    except Exception as e:
        # 2. Security Shield: Hide raw exceptions to prevent data leak and system probing
        print(f"Checkout error for IP {ip}: {e}")
        return jsonify({"error": "Payment checkout initialization failed. Please contact support."}), 500

# 2. Stripe Webhook endpoint
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    
    if not sig_header:
        return jsonify({"error": "Missing signature header"}), 400
        
    try:
        event = stripe_integration.construct_webhook_event(payload, sig_header)
    except Exception as e:
        return jsonify({"error": f"Webhook verification failed: {e}"}), 400
        
    # Handle the checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        email = session.get("customer_email") or session.get("customer_details", {}).get("email") or "unknown@example.com"
        amount = session.get("amount_total", 580)
        
        # Record transaction in database
        database.record_transaction(session_id, email, amount, "completed")
        
        # Check if license is already created for this checkout session
        existing = database.get_license_by_transaction(session_id)
        if not existing:
            license_key = generate_license_key()
            database.create_license(license_key, email, session_id)
            print(f"License {license_key} generated and saved for transaction {session_id}")
            
    return jsonify({"status": "success"})

# 3. Retrieve License Key by Checkout Session ID (Success Redirection checking)
@app.route("/api/checkout-session-status", methods=["GET"])
def checkout_session_status():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error": "Missing session_id parameter"}), 400
        
    session = stripe_integration.retrieve_checkout_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
        
    # Handle properties safely for both mock dict and real Stripe Checkout session object
    if isinstance(session, dict):
        payment_status = session.get("payment_status")
        customer_details = session.get("customer_details") or {}
        email = session.get("customer_email") or customer_details.get("email") or "unknown@example.com"
        amount = session.get("amount_total", 580)
    else:
        payment_status = getattr(session, "payment_status", None)
        customer_details = getattr(session, "customer_details", None) or {}
        email = getattr(session, "customer_email", None) or customer_details.get("email") or "unknown@example.com"
        amount = getattr(session, "amount_total", 580)
        
    if payment_status == "paid":
        # Check database
        license_data = database.get_license_by_transaction(session_id)
        if not license_data:
            # If Stripe says paid, but webhook hasn't processed it yet, generate now synchronously
            
            database.record_transaction(session_id, email, amount, "completed")
            license_key = generate_license_key()
            database.create_license(license_key, email, session_id)
            print(f"Synchronously created license {license_key} for paid session {session_id}")
        else:
            license_key = license_data["license_key"]
            
        return jsonify({
            "status": "paid",
            "license_key": license_key
        })
    else:
        return jsonify({
            "status": payment_status
        })

# 4. API to validate license key
license_validation_log = {}

def is_license_rate_limited(ip, max_requests=10, window_seconds=60):
    """
    Sliding window rate limiter to prevent brute-force probing of license keys.
    """
    now = datetime.datetime.now().timestamp()
    timestamps = license_validation_log.get(ip, [])
    timestamps = [t for t in timestamps if now - t < window_seconds]
    license_validation_log[ip] = timestamps
    
    if len(timestamps) >= max_requests:
        return True
        
    timestamps.append(now)
    return False

@app.route("/api/validate-license", methods=["POST", "OPTIONS"])
def validate_license():
    if request.method == "OPTIONS":
        return jsonify({}), 200
        
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "127.0.0.1"
    if is_license_rate_limited(ip, max_requests=10, window_seconds=60):
        print(f"Security Shield: IP {ip} rate limited on license key validation.")
        return jsonify({"valid": False, "error": "Too many validation attempts. Please try again later."}), 429
        
    try:
        data = request.get_json(force=True) or {}
        license_key = data.get("license_key", "").strip()
        
        if not license_key:
            return jsonify({"valid": False, "error": "License key is required"}), 400
            
        is_valid = database.validate_license(license_key)
        return jsonify({"valid": is_valid})
    except Exception as e:
        print(f"License validation error for IP {ip}: {e}")
        return jsonify({"valid": False, "error": "An error occurred during verification."}), 500

@app.route("/api/gemini-proxy", methods=["OPTIONS"])
def preflight():
    return jsonify({}), 200

@app.route("/api/gemini-proxy", methods=["POST"])
def gemini_proxy():
    data = request.get_json(force=True) or {}

    # 1. License check (validate against SQLite database)
    license_key = request.headers.get("X-License-Key", "").strip()
    is_premium = database.validate_license(license_key)

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

    model = data.get("model", "gemini-3.5-flash")
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
