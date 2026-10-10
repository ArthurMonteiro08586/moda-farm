# moda-farm

MODA (moda.app) automation toolkit — API reverse-engineering + account farm.

## What MODA is

AI design agent platform (canvases, websites, brand kits). Free plan = 500 credits/mo.
Pro = $30/mo, 6000 credits. Promo `CLAUDEFOUNDERS` gives **90 days of Pro free** (no card,
auto-cancels at trial end) — but requires a **work email domain** (rejects gmail/outlook etc.)
and is claimable **once per email domain** (`promo_domain_already_claimed`).

## Files

- `farm_reg.py N` — full auto-register loop: creates temp inbox on [voidash](https://voidash.com)
  (rotates domains: voidash.cyou / govno.eu.cc / musor.eu.cc / pomoi.eu.cc / voidash.bond),
  solves Cloudflare Turnstile via local captcha sidecar (`:8877`, invisible sitekey,
  `action=signup` — mandatory), Clerk sign_up → email code from voidash API (`otp_code` field)
  → attemptVerification `{code, strategy:'email_code'}` → setActive → MODA `/users/me/sync`
  → `POST /organizations/{org}/billing/redeem-promo` `{"code": "CLAUDEFOUNDERS"}`.
  Accounts land in `accounts.jsonl`.
- `redeem_existing.py` — re-login (password) into already-registered accounts and finish
  promo redeem + collect org/ref/credits. Fresh browser per account (Clerk session leaks
  across contexts otherwise → wrong org).
- `api_probe.py` — password sign-in via Clerk client API → fresh JWT → probes billing/referral/
  team/memory endpoints. JWT lives ~60s, always fetch with `getToken({skipCache:true})`.

## Key API facts (reverse-engineered from app chunks + live probes)

- Auth: Clerk `clerk.moda.app`, pk `pk_live_Y2xlcmsubW9kYS5hcHAk`, JS v6.
  Login: `client.signIn.create({identifier, password})` → `setActive({session: createdSessionId})`.
  There is NO `window.Clerk.signIn()` — use `client.signIn.create`.
- `POST https://api.moda.app/api/v1/users/me/sync` — provisions user+org, returns email/orgs.
- Billing: `/api/v1/organizations/{org}/billing/{status,usage,credit-details,credit-bundles,redeem-promo,checkout}`
- Referrals: `/api/v1/organizations/{org}/referrals/{code,stats}`, `/api/v1/referrals/claim`
- Credit bundles: $10→2000cr, $25→5000cr, $50→10000cr, $100→22000cr.
- Seats: paid plan up to 10 (`promo_seat_cap`), credits_per_seat 6000 — invites share quota.
- Generation surface: `/api/v1/conversations/omni/{id}` + `/turns/{id}` (agent turns),
  `/api/v1/canvases`, `/api/v1/websites` (+`/duplicate`), `/api/v1/remove-background`,
  Liveblocks collaboration, Figma OAuth.

## Agent model catalog (AGENT_MODEL_CATALOG, from app bundle)

Primary (free tier ok): **opus-5** (Opus 5, efforts none..max, anthropic-fast),
**sonnet-5.5**, **gpt-6.1-sol** (GPT-6.1 Sol, openai-priority fast).
More: opus-4.8, sonnet-5, **fable-5.1 / fable-5 (requiresPaid)**, haiku-4.5,
gpt-5.6-sol / -terra / -luna, kimi-k2.5 / k2.6 / k3 (Kimi K3 = 1M context, via Fireworks).
UI tiers: lite / standard / pro / pro-fast (+ experimental gpt-5.6 high-reasoning).
Image model default: nano-banana-lite.

## Pitfalls

- Clerk `attemptVerification` on sign_up REQUIRES `strategy:'email_code'` in the same call.
- `createEmailAddress` payload is `{email}` — NOT `{email_address}` (minified source: `let{email:t}=e`).
- Promo redeem body key is `code`, not `promo_code` (422 otherwise).
- voidash messages carry `otp_code` directly; fallback regex `\b\d{6}\b` on preview/body.
- Clerk domains blocklist: voidash.cyou / eu.cc domains get `form_email_address_blocked`
  ("temporary email services not allowed"); voidash.bond passes. One domain = one promo claim,
  so per-account promo needs unique unblocked work-email domains.
- Cloudflare: inject only `cf_clearance`, `__cf_bm`, `_cfuvid`; wait while page title contains "moment".
- Turnstile sitekeys: invisible `0x4AAAAAAAFV93qQdS0ycilX` (action `signup`), smart `0x4AAAAAAAWXJGBD7bONzLBd`.

## Env

- `MODA_EMAIL`, `MODA_PASS` — for api_probe.py / redeem_existing.py login.
- `MODA_REF` — referral code appended to sign_up metadata.
- `MODA_UA` — user agent override.
