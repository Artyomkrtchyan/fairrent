# Live USD/AMD exchange rate

The real-mode frontend reads `GET /api/v1/exchange-rate`, which now loads the
published USD/AMD quote from the Central Bank of Armenia's official SOAP
`ExchangeRatesLatestByISO` service over HTTPS.

- The C01 `ExchangeRate` and `Freshness` shapes are unchanged.
- CBA rates are normalized by their `Amount` field to AMD per 1 USD.
- Each successful result is cached in-process for 15 minutes to reduce calls.
  If the upstream fails after a successful fetch, the original observed date
  is retained. Rates older than seven days are returned as `stale`, disabling
  AMD display rather than silently using outdated data.
- If no provider result exists, the API returns 503 and the frontend stays in
  USD. There is **no** hard-coded or synthetic fallback in real mode.
- No reviewer authorization, secret, contract, or currency-preference changes
  are needed.

## Verify after deployment

1. Open `https://fairrent.online/api/v1/exchange-rate`. Expect HTTP 200,
   `status: available`, a positive `amd_per_usd`, and source/date metadata.
2. On FairRent, switch from USD to AMD and back; prices on listings and reviewer
   pages should update using the same shared formatting.
3. If the API returns 503, check server outbound access to
   `api.cba.am:443` and provider uptime. If it returns `stale`, the toggle
   correctly remains unavailable.

Reference: https://www.cba.am/en/exchange-rates-retrieval/
