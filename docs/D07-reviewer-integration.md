# D07 reviewer frontend integration checkpoint

Owner: @manemazmand. Branch: feat/D07-reviewer-interface. This is an unfinished frontend feature, not verified reviewer authorization.

## Implemented in this checkpoint

- Review queue using C01 `ReviewPage` types, status/category filters, pagination and empty/error/loading states.
- Review detail with original listing, version, grouped signal evidence, audit history and explicit price-versus-risk distinction.
- Decision draft with contract-derived status/decision fields, mandatory reason validation, and visible unsaved state.
- Mock mode reads only the shared `contracts/fixtures.json` review fixture. No synthetic login, writes, or client-side authorization.
- Real mode reads `GET /api/v1/reviews` via the existing typed API client and surfaces 401/403/503 instead of substituting synthetic records.
- The typed `PATCH /api/v1/reviews/{id}` wrapper is prepared but intentionally not wired to the Save button without a reviewed authenticated session mechanism.

## C05 integration needed before completion

PR #75 provides a C05 foundation with expiring/revocable opaque bearer sessions provisioned by an administrator, but **not interactive sign-in**. Coordinate with Artyom on approved session delivery and lifecycle, browser exposure, expiry/revocation, role enforcement and CSRF/CORS assumptions. Do not add credentials to VITE_* environment variables or localStorage. The backend must enforce authorization; frontend route hiding is not access control.

After the approved identity/session design is agreed, add only the intended auth boundary; connect the Save action to the existing typed `updateReview` function, passing the latest `version`, and disable re-submission during mutation. On 409, refresh the current queue case and require a new decision; on 401/403, clear any auth context and show access state. Reconcile 422 and backend transition rules with the C05 owner. Do not claim a decision was saved without a 200 response and a returned review history.

The C01 contract has GET queue and PATCH case, but **no GET case-by-id**. Current detail resolves a case by paginating the queue (bounded to 50 pages); if C05 later adds a specific endpoint, agree to update the contract before using it. Real, large-queue performance and case visibility require verification.

## Validation checklist

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run lint
npm run build
```

Then check mock queue filters, review draft validation, history/evidence text, 401/403/409 error handling and mobile/keyboard usability. Real session tests and persistence tests remain blocked on the approved C05 browser sign-in integration. No local checks were run as part of this remote GitHub edit.

## Display currency

The review queue and review details now reuse the existing `Money` and `RateNote` components and global `usePrefs` currency setting. Canonical API values remain USD. Display switches to AMD only when the shared exchange-rate response permits conversion, matching D02–D06. No fixed rate is introduced and no new preference state is created. Verify the header USD/AMD toggle on both review routes, including rate-unavailable behavior.
