# SocialIntent API Proxy

Gemini APIプロキシサーバー。Render.comにデプロイしてSocialIntentのバックエンドとして使用します。

## エンドポイント

- `GET /` — ヘルスチェック
- `POST /api/gemini-proxy` — Gemini APIへのプロキシ（レート制限付き）

## 環境変数（Renderで設定）

| 変数名 | 説明 |
|--------|------|
| `GEMINI_API_KEY` | Google AI StudioのGemini APIキー |

## デプロイ手順（Render）

1. GitHubにこのフォルダをpush
2. render.com → New → Web Service → リポジトリを選択
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Environment Variables: `GEMINI_API_KEY` を設定
