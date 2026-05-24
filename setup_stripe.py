# -*- coding: utf-8 -*-
import os
import sys
import stripe

def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_stripe.py <STRIPE_SECRET_KEY>")
        sys.exit(1)
        
    secret_key = sys.argv[1].strip()
    if not (secret_key.startswith("sk_test_") or secret_key.startswith("sk_live_")):
        print("Error: Invalid API key format. Key should start with 'sk_test_' or 'sk_live_'.")
        sys.exit(1)
        
    stripe.api_key = secret_key
    
    # Target Webhook URL for Render production
    webhook_url = "https://socialintent-api.onrender.com/webhook/stripe"
    
    try:
        print(f"Connecting to Stripe and registering Webhook URL: {webhook_url}...")
        
        # Check if endpoint already exists to avoid duplicates
        existing_endpoints = stripe.WebhookEndpoint.list()
        target_endpoint = None
        for ep in existing_endpoints.auto_paging_iter():
            if ep.url == webhook_url and ep.status == "enabled":
                target_endpoint = ep
                print("Found existing enabled webhook endpoint.")
                break
                
        if not target_endpoint:
            # Create a new webhook endpoint via Stripe API
            target_endpoint = stripe.WebhookEndpoint.create(
                url=webhook_url,
                enabled_events=["checkout.session.completed"]
            )
            print("Webhook endpoint successfully registered on your Stripe account!")
            
        webhook_secret = target_endpoint.secret
        
        # Write to .env file
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        gemini_key = ""
        
        # Load existing GEMINI_API_KEY if present
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        gemini_key = line.strip()
                        
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"STRIPE_SECRET_KEY={secret_key}\n")
            f.write(f"STRIPE_WEBHOOK_SECRET={webhook_secret}\n")
            if gemini_key:
                f.write(f"{gemini_key}\n")
            else:
                f.write("GEMINI_API_KEY=your_gemini_api_key_here\n")
                
        print("\n=== Setup Completed Successfully ===")
        print(f".env file created at: {env_path}")
        print("Stripe Secret Key and Webhook Secret have been automatically configured!")
        
    except Exception as e:
        print(f"\nError registering Stripe Webhook: {e}")
        print("Please check if your Stripe Secret Key is valid and has Webhook write permissions.")
        sys.exit(1)

if __name__ == "__main__":
    main()
