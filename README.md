# Intrinsic — instant DCF stock valuation

Type a ticker, get a two-stage discounted cash flow valuation built from
free market data, with adjustable growth and discount rate assumptions.

## What it does

- Pulls financial statements for a ticker via `yfinance` (free, no API key)
- Computes a default revenue growth rate from 5-year historical CAGR
- Computes a default WACC: CAPM cost of equity plus after-tax cost of debt,
  weighted by debt and market equity
- Projects unlevered free cash flow 5 years forward, discounts it back,
  adds a Gordon growth terminal value, and subtracts net debt
- Shows fair value per share next to the current market price, in the
  stock's own currency
- Flags tickers that do not suit a standard DCF: banks and financial
  institutions, loss-making companies, and companies with too little
  trading history
- Lets you drag growth rate and WACC/discount rate and watch fair value update
- Every input the DCF uses is visible and adjustable: growth rate, WACC,
  risk-free rate, beta, equity risk premium, cost of debt, debt weight, EBIT
  margin, tax rate, D&A %, CapEx %, working capital change %, and terminal
  growth. Anything you have not touched stays at its computed default, and
  dragging one of the WACC build-up inputs recomputes the discount rate
  automatically unless you have overridden that directly
- Shows a sensitivity grid across growth/discount rate combinations, shaded
  by how large the resulting gap is
- Plots 5 years of price history with today's fair value drawn across it
- Compares trailing P/E, EV/EBITDA, and P/S against the DCF-implied P/E and
  a sector peer average, and also solves for the growth rate the current
  market price would imply, so a disagreement between the model and the
  market becomes a specific number instead of a vague "overvalued" label
- EBIT margin, D&A %, CapEx %, and working capital % are computed as the
  median year-by-year ratio rather than a plain average, so one badly
  mismatched year (a misclassified line item, or figures pulled from a
  different restated vintage of a company's filings) does not silently
  drag the whole default off course
- For plain US tickers (no exchange suffix), pulls financial statements
  from SEC EDGAR's free, keyless XBRL data instead of yfinance, since it
  comes standardized directly from a company's own regulatory filings and
  naturally prefers the most recently filed (restated) figures. Falls
  back to yfinance automatically if EDGAR doesn't have usable data
- Uses the actual Euro-area 10-year rate from the ECB for EUR- and
  DKK-denominated companies, instead of the US Treasury yield for every
  currency
- Optionally cross-checks non-US tickers against Financial Modeling
  Prep's free tier, flagging it when the two sources disagree by more
  than 15% on revenue or operating income (needs a free FMP API key, see
  Setup below; skipped entirely if not configured)
- Detects when a stock's financial statements are reported in a different
  currency than it trades in (common for cross-listed shares, like a
  Danish company's stock also trading in Frankfurt), and converts using a
  live FX rate, or flags the result as unreliable if no rate is available,
  instead of silently mixing two currencies into one fair value
- When the computed fair value gap versus the market price exceeds 150%,
  the app shows a visibly different "unreliable result" state instead of
  a normal-looking undervalued/overvalued card, since a gap that large is
  almost always a data problem, not a real mispricing
- Backtest reruns the model at every historical checkpoint the free data
  allows (typically 2-3), using historical debt, cash, and price where
  available so the WACC and net-debt bridge are time-consistent
  rather than treating one historical guess as a verdict
- Sensitivity grid highlights the cell matching your current live
  assumptions, so you can see where you sit inside the table at a glance
- Lets you save tickers to a local watchlist and compare them side by side
- Search box autocompletes both tickers and company names as you type,
  using Yahoo Finance's free search endpoint
- All key assumptions are laid out in one full-width panel, grouped into
  core / WACC build-up / operating assumptions, each with its own reset
  icon so you can undo a single override without resetting everything

## Structure

```
backend/     FastAPI service, the DCF model, and the yfinance data pipeline
frontend/    React + TypeScript app (Vite)
```

See `backend/README.md` and the sections below for run and deploy instructions.

## Run locally

Backend:

    cd backend
    python -m venv venv
    source venv/bin/activate   # on Windows: venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env       # optional: add an FMP_API_KEY here, see below
    uvicorn app.main:app --reload --port 8000

### Optional: enabling Financial Modeling Prep

1. Sign up for a key at Financial Modeling Prep.
2. Put it in `backend/.env` as `FMP_API_KEY=your-key-here`.
3. Optional: add `FMP_API_KEY_2` and `FMP_API_KEY_3` as backup keys. The backend uses key 2 only if key 1 hits quota/rate limits, and key 3 only if keys 1 and 2 both hit quota/rate limits.
4. Restart uvicorn.

Without a key, the Yahoo DCF tab still works. The FMP DCF tab needs an FMP key.

Frontend (in a second terminal):

    cd frontend
    npm install
    cp .env.example .env       # points the frontend at localhost:8000
    npm run dev

Then open the URL Vite prints (usually http://localhost:5173).

## Deploy for free

**Backend on Render:**
1. Push this repo to GitHub.
2. On Render, create a new Web Service from the repo, root directory `backend`.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Render's free tier spins down after inactivity, so the first request
   after idle time can take 15 to 30 seconds. Fine for a portfolio project.

**Frontend on Vercel:**
1. Import the repo on Vercel, root directory `frontend`.
2. Framework preset: Vite.
3. Add an environment variable `VITE_API_BASE_URL` pointing at your Render
   backend URL (e.g. `https://your-app.onrender.com`).
4. Deploy.

## Known limitations (v1)

- The ECB risk-free rate call uses a specific series key from the ECB
  Data Portal's free API that has not been verified against a live
  request, since this was built somewhere without internet access. If it
  turns out to be wrong, it fails safe (falls back to the US Treasury
  rate) rather than crashing, but it's worth double-checking the series
  key in `backend/app/pipeline/ecb.py` against ECB's own documentation
  the first time this runs somewhere with real network access.
- SEC EDGAR data is used only for plain US tickers (no exchange suffix,
  like `AAPL` rather than `AAPL.MX`), and only when EDGAR has at least 3
  years of usable revenue and EBIT data for that company. Working-capital
  change is not pulled from EDGAR (there is no single clean XBRL concept
  for it across filers), so it defaults to 0 for SEC-sourced tickers,
  which understates or overstates cash flow slightly depending on the
  company.
- The FMP cross-check only compares the most recent fiscal year's revenue
  and operating income, and only ever produces a warning; it never
  changes which numbers the DCF actually uses. It's also rate-limited by
  FMP's free tier (250-300 requests/day as of when this was built, worth
  confirming current limits), shared across every user of the app if
  deployed publicly with one shared key.
- The currency mismatch fix converts raw statement line items (revenue,
  EBIT, cash flow, balance sheet) using a live spot FX rate on the date the
  app is run. It does not restate historical years at the FX rate that
  applied in each of those years, so multi-year ratios (margins, growth)
  carry a small amount of FX-driven noise even after conversion.
- The DCF assumes a constant capital structure and uses an unlevered FCFF approach. Enterprise value is bridged to equity value by subtracting net debt.
- Equity risk premium (5%) and terminal growth (2.5%) are shown as
  defaults but are fully adjustable, same as every other assumption.
- Works best for large, profitable, non-financial companies. Banks,
  insurers, and loss-making companies get a caveat instead of a number,
  since a standard FCF DCF does not fit their business model.
- `yfinance` data quality varies for smaller or non-US tickers. Test with
  large, well-known names first.
- The sector peer comparison uses a small static list of large, liquid
  peers per sector (see `backend/app/models/peers.py`), not a full sector
  index, so treat it as a rough sanity check, not a precise benchmark.
- The backtest reuses today's shares outstanding and beta as approximations
  for their historical values, since free point-in-time data for those is
  not reliably available. It also only has 2 years of holdout to test
  against, since `yfinance`'s free annual statement history is short.
  Read it as directional evidence, not a precise replay.
- The watchlist is stored in the browser's local storage, so it is
  per-browser and does not sync across devices.
- Autocomplete calls Yahoo's public search endpoint directly with a plain
  `requests` call, since yfinance itself does not wrap it. It is best-effort:
  network hiccups or Yahoo rate limiting just show no suggestions rather
  than an error, and you can still type an exact ticker and hit "Value it".

## Roadmap ideas

- Comparable-company valuation as a full second method alongside DCF.
- Shareable valuation links (ticker + assumptions encoded in the URL).
- Server-side watchlist persistence if you want it to sync across devices.

## License

MIT. Use it, fork it, extend it.


## FMP direct DCF mode

Create `backend/.env` with:

```env
FMP_API_KEY=your_primary_key_here
FMP_API_KEY_2=your_second_key_here
FMP_API_KEY_3=your_third_key_here
FMP_ONLY=1
FMP_DIRECT_DCF=1
FMP_PRICE_HISTORY=0
```

With `FMP_DIRECT_DCF=1`, the headline fair value shown in the FMP tab comes from Financial Modeling Prep's own prebuilt DCF endpoint. The app still calculates and displays its own transparent internal DCF assumptions, projected FCFF, sensitivity table, and diagnostics, so those panels will not exactly reconcile to the FMP headline value.

`FMP_API_KEY_2` and `FMP_API_KEY_3` are optional quota-fallback keys. They are not used in round-robin mode: key 1 is always tried first, key 2 is used only after a quota/rate-limit response from key 1, and key 3 is used only after quota/rate-limit responses from keys 1 and 2.

Set `FMP_DIRECT_DCF=0` if you want the headline fair value to use the internal model instead.

## Latest workflow notes

- The app now opens on the **Yahoo / Internal DCF** tab by default. This tab does not call FMP, so users can search multiple tickers without burning FMP API quota.
- The **FMP DCF** tab is loaded only when the user explicitly clicks it. FMP Direct DCF responses are cached for the configured TTL, so switching back to the same ticker or changing assumptions reuses cached data.
- Both tabs include scenario presets: **Conservative**, **Neutral**, **Bullish**, and **Custom**. Presets stage assumption changes; the model updates when the user presses **Calculate DCF**.
- Company-name searches such as `apple` now show clickable ticker choices before valuation instead of trying to value a fake ticker like `APPLE`.
