# FairRent frontend

React, TypeScript and Vite frontend for long-term apartment rentals in
Yerevan. Uses TanStack Router, TanStack Query and Tailwind CSS.

## Requirements

- Node.js 24 LTS
- npm
- Run commands inside `frontend/`.
- Keep the repository's `contracts/` directory alongside `frontend/`.

## Install and run

```bash
npm ci
```

```bash
npm run dev
```

Open the local address printed by Vite.

## API modes

Mock mode is the default. It uses synthetic examples from
`../contracts/fixtures.json`; these are not real listings or model results.

Explicit mock mode:

```bash
VITE_API_MODE=mock npm run dev
```

Real mode:

```bash
VITE_API_MODE=real VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Real mode requires accessible backend business endpoints. A different API
origin must allow the frontend through CORS. Failed requests show errors;
they do not silently fall back to mock data.

Optional local settings can be placed in `.env.local`, using `.env.example`
as a reference. Restart the development server after changing settings.
All VITE_* variables are browser-visible: never put credentials in them.

Mock transport does not implement server-side filtering, authentication
or database writes.

## Currency and theme

The interface supports light, dark and system themes.

USD is the canonical price currency. AMD display conversion uses the
shared exchange-rate response. Mock rates are explicitly synthetic.
AMD conversion is unavailable when the rate fails the freshness or
availability checks.

Display rounding: USD to two decimals, AMD to whole dram, half up.
Currency selection does not change the underlying USD amounts.

## Checks

```bash
npm run typecheck
```

```bash
npm test
```

```bash
npm run lint
```

```bash
npm run build
```

Lint currently reports eight Fast Refresh warnings about mixed
component/helper exports. There are no lint errors at the last check.

## API types

Regenerate types after agreed OpenAPI changes:

```bash
npm run generate:api
```

Types are generated from `../contracts/openapi.json` into
`src/api/schema.d.ts`. Do not edit the generated file manually.

## Production build

```bash
npm run build
```

Static output is written to `dist/`.

```bash
npm run preview
```

Preview serves the last production build, so rebuild after code changes.

Production hosting must serve `index.html` for frontend routes such as
`/analytics`, while preserving asset and API routing. AWS deployment
configuration remains part of the infrastructure tasks.

## D02 scope

Implemented:
- Responsive shared layout, navigation and theme selection.
- Typed API client with mock and real transports.
- C01-backed catalogue and basic listing details.
- USD/AMD display conversion through the shared rate response.
- Loading, error, missing-value and not-found handling.

Later tasks:
- Complete filters, sorting, pagination and URL state: D03.
- Full listing valuation and evidence presentation: D04.
- Interactive map and infrastructure layers: D05.
- Integrated analytics: D06.
- Reviewer authentication and mutations: D07.
- Final end-to-end verification: D08.
- Integrated coordinate assessment: D09.

Analytics, coordinate and reviewer preview screens may still use separate
synthetic demonstration data. Their presence does not mean backend
integration is complete. Demo photographs do not depict actual listings.