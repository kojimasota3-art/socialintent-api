# -*- coding: utf-8 -*-
import os
import random
import string
import stripe

# Initialize Stripe with the API key from environment variables
stripe_secret = os.environ.get("STRIPE_SECRET_KEY")
webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Check if we should run in mock mode
is_mock_mode = False
if not stripe_secret or stripe_secret.startswith("sk_test_mock"):
    is_mock_mode = True
    print("Stripe integration: STRIPE_SECRET_KEY not configured. Running in Mock/Simulation mode.")
else:
    stripe.api_key = stripe_secret
    print("Stripe integration: Real Stripe Secret Key loaded successfully.")

def create_checkout_session(email, origin):
    """
    Creates a Stripe Checkout Session for a one-time payment of ¥580
    for the "SocialIntent AI - Viral Planner Premium" lifetime access.
    """
    if not origin:
        origin = "http://localhost:10000"
        
    if is_mock_mode:
        # Simulate Stripe Checkout redirection url locally
        random_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
        session_id = f"mock_session_{random_id}"
        # We redirect directly back to success url with the mock session ID
        mock_url = f"{origin}/index.html?checkout_success=true&session_id={session_id}"
        return {
            "id": session_id,
            "url": mock_url
        }
        
    try:
        # Stripe Checkout automatically enforces EMV 3-D Secure (3DS2) and Strong Customer Authentication (SCA)
        # to satisfy Japanese and global anti-fraud laws. Stripe Radar also performs advanced fraud checks
        # on every session creation and card input attempt to prevent automated Credit Master attacks.
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_email=email if email else None,
            line_items=[
                {
                    'price_data': {
                        'currency': 'jpy',
                        'product_data': {
                            'name': 'SocialIntent AI - Viral Planner Premium',
                            'description': 'Lifetime Access (買い切り)',
                        },
                        'unit_amount': 580, # ¥580
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            success_url=f"{origin}/index.html?checkout_success=true&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/index.html?checkout_cancel=true",
        )
        return {
            "id": session.id,
            "url": session.url
        }
    except Exception as e:
        print(f"Error creating stripe session: {e}")
        raise e

def construct_webhook_event(payload, sig_header):
    """
    Verifies and constructs the Stripe Webhook Event.
    """
    if is_mock_mode:
        # In mock mode, we don't verify real signatures
        return {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "mock_session_webhook",
                    "customer_email": "customer@mock.com",
                    "amount_total": 580
                }
            }
        }
        
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except ValueError as e:
        print("Invalid payload for webhook")
        raise e
    except stripe.error.SignatureVerificationError as e:
        print("Invalid signature for webhook")
        raise e

def retrieve_checkout_session(session_id):
    """
    Retrieves a Stripe Checkout Session by ID.
    """
    if is_mock_mode or (session_id and session_id.startswith("mock_session_")):
        # Mock retrieval of successful payment
        return {
            "id": session_id,
            "payment_status": "paid",
            "customer_details": {
                "email": "customer@mock.com"
            },
            "amount_total": 580
        }
        
    try:
        return stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        print(f"Error retrieving stripe session {session_id}: {e}")
        return None
