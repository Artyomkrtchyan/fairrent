# D09 — Coordinate valuation and observed market dispersion

**Issue:** [#37](https://github.com/Artyomkrtchyan/fairrent/issues/37) · **Dependency:** [C11 #36](https://github.com/Artyomkrtchyan/fairrent/issues/36)

## User workflow

1. Open **Location assessment** and select a Yerevan point on the embedded map, or type latitude and longitude.
2. Assess using only coordinates to obtain an **area reference**. If floor area is provided, request a **property assessment**; a room count can refine the property input and requires floor area.
3. The frontend sends `POST /api/v1/valuations` with validated coordinates, a 1,000-m radius and a 30-day window, plus optional property features.
4. Review the market assessment, comparable count, search radius, observation dates and data freshness.
5. Review observed mean rent and standard deviation in **USD/month** and **USD/m²/month**. This statistical dispersion is **not** a calibrated property prediction interval.
6. API validation and network errors are shown without generating a synthetic result. Null statistics remain **Not available**.

## Map interoperability

The valuation page uses the existing shared MapLibre canvas through two optional props: `onPickCoordinate` and `pickedCoordinate`. The catalogue map is unchanged; its nearby university and metro layers remain available there. Clicking the valuation map updates coordinates and clears the previous result so that it cannot be mistaken for a new-location assessment.

## Test coverage

`frontend/src/test/valuation-form.test.tsx` covers coordinate-only and property requests, coordinate selection, positive-area input validation, displayed assessment and API errors. The established frontend and Chromium browser workflows run in GitHub Actions.

Manual acceptance checklist (record result before closing D09):

- [ ] Map click sets accurate displayed coordinates; manual edits and keyboard input work.
- [ ] Coordinate-only response labels the result as an area reference.
- [ ] Property assessment accepts valid area and optional room count; invalid/out-of-coverage inputs display errors.
- [ ] Real API returns comparable counts, observation time window, source freshness and units accurately.
- [ ] Sparse/no-comparable response does not invent a price or zero deviation.
- [ ] Observed standard deviation remains distinct from prediction interval.
- [ ] Verify mobile layout and the existing metro/university layers on the catalogue map remain functional.
- [ ] Record date, browser, deployed commit and redacted acceptance screenshots after deployment.

**Important:** Passing fixture-backed CI does not independently verify all production live-data cases. Do not mark the above manual checks complete without evidence.
