from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
import datetime
import requests

app = FastAPI(title="SocialIntent API Proxy", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory rate limiter: date_str -> ip -> count
proxy_usage: dict = {}


class GeminiPayload(BaseModel):
    contents: List[dict]
    model: str = "gemini-2.0-flash"


@app.get("/")
async def root():
    return {"status": "ok", "service": "SocialIntent API Proxy"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/gemini-proxy")
async def gemini_proxy(payload: GeminiPayload, request: Request):
    # 1. License check
    license_key = request.headers.get("X-License-Key", "")
    is_premium = license_key.strip().upper().startswith("LS-") and len(license_key.strip()) >= 10

    # 2. Client IP
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else (
        request.client.host if request.client else "127.0.0.1"
    )

    # 3. Rate limit (3 req/day for free tier)
    if not is_premium:
        today = datetime.date.today().isoformat()
        # Clean old dates
        for d in list(proxy_usage.keys()):
            if d != today:
                proxy_usage.pop(d, None)
        proxy_usage.setdefault(today, {})
        count = proxy_usage[today].get(ip, 0)
        if count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="無料枠の上限（1日3回）に達しました。プレミアムライセンスをご登録ください。",
            )
        proxy_usage[today][ip] = count + 1

    # 4. Forward to Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured on server")

    model = payload.model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        res = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"contents": payload.contents},
            timeout=30,
        )
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
