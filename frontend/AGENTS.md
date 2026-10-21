## Repository workflow

- This frontend belongs to Artyomkrtchyan/fairrent.
- Work on a focused task branch from updated main.
- Follow the repository's CONTRIBUTING.md and docs/git-workflow.md.
- Preserve the shared C01 API contract; coordinate changes with affected owners.
- Run frontend type checks, tests, lint and build before requesting review.
- Commit, push and merge only when explicitly authorized by the user.
- Branding changes require agreement before implementation.

## Architecture
- Demo data lives in src/lib/data.ts as synthetic static data with USD as the canonical unit; UI converts for display only so filters and storage never depend on the display currency.
- Theme and currency preferences live in src/lib/prefs.tsx (React context + localStorage, read in effects) so SSR markup stays hydration-safe.
- Price comparison status is derived only from the calibrated interval (priceStatus) so every page labels listings consistently; covered by src/test/price-status.test.ts.
- Listing photos are synthetic demo images keyed by each listing's `thumbnailUrl` in src/lib/photos.ts; every photo area keeps its visible "Demo image" label and the "Photo unavailable" fallback when no image is assigned or it fails to load; covered by src/test/listing-photo.test.tsx.
