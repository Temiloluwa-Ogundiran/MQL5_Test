# MQL5 Execution Test

## Purpose
Test EA execution layer. No strategy. Demo only.

## Setup
1. Add `https://mql5.temiloluwa.dev` to MT5 -> Tools -> Options -> Expert Advisors -> Allow WebRequest.
2. Run `docker compose up --build -d`.
3. Open `https://mql5.temiloluwa.dev/docs` to send intent.

## Use
POST `/intents` with `signal_id`, `account_id`, `symbol`, `direction`, `lots`, `sl`, `tp`, `generated_at` (UTC).
EA polls `GET /intents/next?account_id=<login>` and executes.
Check `GET /reports?signal_id=TEST-001`. Check `GET /intents/{signal_id}` for history.

## Compose
No host ports. Only `expose`. Dokploy maps domain `mql5.temiloluwa.dev` to `api:8000`.

## EA Inputs
- `BackendURL` - default `https://mql5.temiloluwa.dev`
- `PollSec` - poll interval, default `3`
- `StaleSec` - max age, default `120`
- `DeviationPoints` - slippage, default `10`

## Verification
1. `docker compose config` - verify no `ports`, only `expose`.
2. `docker compose up --build -d` - verify api and db start.
3. POST intent via `/docs` then check EA Experts log and `GET /reports?signal_id=TEST-001`.
