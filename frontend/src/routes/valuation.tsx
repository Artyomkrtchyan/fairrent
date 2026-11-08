import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { lazy, Suspense, useState, type FormEvent } from "react";
import { requestValuation } from "@/api/valuations";
import { MarketAssessment } from "@/components/MarketAssessment";
import { PageHeader } from "@/components/ui-bits";

const MapCanvas = lazy(() =>
  import("@/components/MapCanvas").then((module) => ({ default: module.MapCanvas })),
);

export const Route = createFileRoute("/valuation")({
  head: () => ({
    meta: [
      { title: "Location rent assessment — FairRent" },
      {
        name: "description",
        content:
          "Get an area rent reference for Yerevan coordinates, optionally refined with apartment details.",
      },
      { property: "og:title", content: "Location rent assessment — FairRent" },
      {
        property: "og:description",
        content: "Area reference rents for a Yerevan location.",
      },
    ],
  }),
  component: Valuation,
});

const field = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm";
const INITIAL_LAT = "40.1872";
const INITIAL_LNG = "44.5152";

function usdStatistic(value: number | null, unit: string) {
  return value === null ? "Not available" : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value)} ${unit}`;
}

function coordinateIsValid(latitude: number, longitude: number) {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

export function Valuation() {
  const [lat, setLat] = useState(INITIAL_LAT);
  const [lng, setLng] = useState(INITIAL_LNG);
  const [rooms, setRooms] = useState("");
  const [area, setArea] = useState("");
  const [error, setError] = useState<string | null>(null);
  const valuation = useMutation({ mutationFn: requestValuation, retry: false });
  const latitude = Number(lat);
  const longitude = Number(lng);
  const selectedCoordinate =
    lat.trim() && lng.trim() && coordinateIsValid(latitude, longitude)
      ? { latitude, longitude }
      : null;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (valuation.isPending) return;

    valuation.reset();
    const areaSqm = area.trim() === "" ? undefined : Number(area);
    if (!lat.trim() || !lng.trim() || !coordinateIsValid(latitude, longitude)) {
      setError("Enter a valid latitude and longitude.");
      return;
    }
    if (areaSqm !== undefined && (!Number.isFinite(areaSqm) || areaSqm <= 0)) {
      setError("Floor area must be greater than zero.");
      return;
    }
    if (rooms !== "" && areaSqm === undefined) {
      setError("Enter floor area when selecting a room count for a property assessment.");
      return;
    }
    setError(null);
    valuation.mutate({
      latitude,
      longitude,
      radius_m: 1000,
      window_days: 30,
      ...(areaSqm !== undefined ? { area_sqm: areaSqm } : {}),
      ...(rooms ? { rooms: Number(rooms) } : {}),
    });
  };

  const statistics = valuation.data?.observed_market_statistics;
  const cohort = valuation.data?.cohort;
  const areaReference = valuation.data?.kind === "area_reference";

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Location assessment"
        intro="Select a spot on the map or enter coordinates. Add apartment details to request a property assessment."
      />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <section className="card-surface p-5" aria-labelledby="choose-location-title">
            <h2 id="choose-location-title" className="text-lg font-semibold">
              Choose a location
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Click anywhere on the map to set the coordinates below. You can still type coordinates manually.
              Map locations are approximate references, not verified building addresses.
            </p>
            <div className="mt-4 overflow-hidden rounded-lg border">
              <div className="relative h-80 [&_.map-canvas]:!h-full">
                <Suspense fallback={<p role="status" className="p-4">Loading map…</p>}>
                  <MapCanvas
                    onPickCoordinate={(nextLatitude, nextLongitude) => {
                      setLat(nextLatitude.toFixed(6));
                      setLng(nextLongitude.toFixed(6));
                      setError(null);
                      valuation.reset();
                    }}
                    pickedCoordinate={selectedCoordinate}
                  />
                </Suspense>
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground" role="status">
              {selectedCoordinate
                ? `Selected: ${selectedCoordinate.latitude.toFixed(6)}, ${selectedCoordinate.longitude.toFixed(6)}`
                : "Enter valid coordinates or choose a point on the map."}
            </p>
          </section>
          <form onSubmit={submit} className="card-surface space-y-4 p-5" noValidate>
            <h2 className="text-lg font-semibold">Assessment details</h2>
            <fieldset className="grid grid-cols-2 gap-3">
              <legend className="mb-2 text-sm font-bold">Location (required)</legend>
              <label className="text-xs font-semibold">
                Latitude
                <input
                  className={field}
                  inputMode="decimal"
                  value={lat}
                  onChange={(e) => { setLat(e.target.value); valuation.reset(); }}
                  required
                />
              </label>
              <label className="text-xs font-semibold">
                Longitude
                <input
                  className={field}
                  inputMode="decimal"
                  value={lng}
                  onChange={(e) => { setLng(e.target.value); valuation.reset(); }}
                  required
                />
              </label>
            </fieldset>
            <fieldset className="grid grid-cols-2 gap-3">
              <legend className="mb-2 text-sm font-bold">Apartment (optional)</legend>
              <label className="text-xs font-semibold">
                Rooms
                <select className={field} value={rooms} onChange={(e) => { setRooms(e.target.value); valuation.reset(); }}>
                  <option value="">—</option>
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="3">3</option>
                  <option value="4">4</option>
                </select>
              </label>
              <label className="text-xs font-semibold">
                Floor area (m²)
                <input
                  className={field}
                  type="number"
                  min="0"
                  step="any"
                  value={area}
                  onChange={(e) => { setArea(e.target.value); valuation.reset(); }}
                />
              </label>
            </fieldset>
            <p className="text-xs text-muted-foreground">
              Coordinates alone request an area reference. Add floor area for a property assessment;
              room count further refines the subject when provided.
            </p>
            {(error || valuation.error) && (
              <p role="alert" className="text-sm font-semibold text-destructive">
                {error ?? valuation.error?.message}
              </p>
            )}
            <button
              type="submit"
              disabled={valuation.isPending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {valuation.isPending ? "Assessing location…" : "Assess location"}
            </button>
          </form>
        </div>

        <section aria-live="polite" className="space-y-4">
          {valuation.isPending && <p role="status">Loading market evidence…</p>}
          {!valuation.data && !valuation.isPending && !valuation.error && !error && (
            <div className="card-surface p-6 text-sm text-muted-foreground">
              Results will appear here after you assess the selected location.
            </div>
          )}
          {valuation.data && statistics && (
            <>
              <MarketAssessment estimate={valuation.data} />
              <section className="card-surface p-5" aria-labelledby="observed-rents-title">
                <h2 id="observed-rents-title" className="text-lg font-semibold">
                  Observed market dispersion
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  These figures describe the spread of asking rents in comparable listings.
                  Standard deviation is <strong>not</strong> a confidence interval or the
                  model's property prediction range.
                </p>
                <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Comparable rentals</dt>
                    <dd className="mt-1 font-semibold">{statistics.comparables_count}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Reference type</dt>
                    <dd className="mt-1 font-semibold">{areaReference ? "Area reference" : "Property assessment"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Mean monthly rent (USD/month)</dt>
                    <dd className="mt-1 font-semibold">
                      {usdStatistic(statistics.cluster_mean_price_usd, "USD/month")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Monthly rent standard deviation (USD/month)</dt>
                    <dd className="mt-1 font-semibold">
                      {usdStatistic(statistics.observed_price_std_dev_usd, "USD/month")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Mean rent per m² (USD/m²/month)</dt>
                    <dd className="mt-1 font-semibold">
                      {usdStatistic(statistics.cluster_mean_price_per_sqm_usd, "USD/m²/month")}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Rent standard deviation per m² (USD/m²/month)</dt>
                    <dd className="mt-1 font-semibold">
                      {usdStatistic(statistics.observed_price_std_dev_per_sqm_usd, "USD/m²/month")}
                    </dd>
                  </div>
                </dl>
                {statistics.comparables_count === 0 && (
                  <p className="mt-4 rounded-md border p-3 text-sm">
                    No comparable rentals were found for this location and search period.
                    A reliable market dispersion estimate is unavailable.
                  </p>
                )}
                <div className="mt-4 border-t pt-4 text-sm">
                  <h3 className="font-semibold">Evidence coverage</h3>
                  <p className="mt-1 text-muted-foreground">
                    Search radius: {cohort?.radius_m ?? "Unavailable"} metres
                    {cohort && ` · Observation period: ${cohort.period_start} to ${cohort.period_end}`}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Display may use your selected currency. The underlying market statistics
                    and their standard deviations are defined in USD/month and USD/m²/month.
                    Missing values are shown as unavailable rather than zero.
                  </p>
                </div>
              </section>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
