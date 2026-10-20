<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture
- Demo data lives in src/lib/data.ts as synthetic static data with USD as the canonical unit; UI converts for display only so filters and storage never depend on the display currency.
- Theme and currency preferences live in src/lib/prefs.tsx (React context + localStorage, read in effects) so SSR markup stays hydration-safe.
- Price comparison status is derived only from the calibrated interval (priceStatus) so every page labels listings consistently; covered by src/test/price-status.test.ts.
- Listing photos are synthetic demo images keyed by each listing's `thumbnailUrl` in src/lib/photos.ts; every photo area keeps its visible "Demo image" label and the "Photo unavailable" fallback when no image is assigned or it fails to load; covered by src/test/listing-photo.test.tsx.
