# Backend — Instant Stock Valuation API

FastAPI service that fetches financials via yfinance and runs a two-stage
free-cash-flow-to-equity DCF.

## Run locally

    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

Then GET http://localhost:8000/api/valuation/AAPL

Optional FMP configuration in `backend/.env`:

```env
FMP_API_KEY=your_primary_key_here
FMP_API_KEY_2=your_second_key_here
FMP_API_KEY_3=your_third_key_here
FMP_ONLY=1
FMP_DIRECT_DCF=1
FMP_PRICE_HISTORY=0
```

Backup keys are quota fallback only: key 2 is used only if key 1 hits an FMP quota/rate limit, and key 3 is used only if both earlier keys hit quota/rate limits.

## Deploy free

Render.com free web service tier works well:
- Build command: pip install -r requirements.txt
- Start command: uvicorn app.main:app --host 0.0.0.0 --port $PORT

## Cache behavior

The backend caches ticker source data, FMP DCF endpoint responses, peer data,
backtest data, and price-history responses for 6 hours by default.

Locally, this uses in-process memory. On Vercel/serverless, use Upstash Redis
for a real shared cache across users and function instances:

```env
APP_CACHE_TTL_SECONDS=21600
UPSTASH_REDIS_REST_URL=your_upstash_rest_url
UPSTASH_REDIS_REST_TOKEN=your_upstash_rest_token
```

Manual assumption changes recalculate the DCF from cached base data. They should
not spend another FMP call unless the ticker cache is missing or expired.

## API usage behavior

The Yahoo/Internal DCF route (`dcf_view=yfinance`) is designed not to call FMP. The FMP route (`dcf_view=fmp`) is the only route that fetches FMP Direct DCF data. FMP JSON responses are cached for 6 hours by default, or for `APP_CACHE_TTL_SECONDS` if configured.
