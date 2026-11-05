import { useMutation } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { requestValuation } from "@/api/valuations";
import { MarketAssessment } from "@/components/MarketAssessment";
import { Money, PageHeader } from "@/components/ui-bits";

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

export function Valuation() {
  const [lat, setLat] = useState("40.1872");
  const [lng, setLng] = useState("44.5152");
  const [rooms, setRooms] = useState("");
  const [area, setArea] = useState("");
  const [error, setError] = useState<string | null>(null);
  const valuation = useMutation({ mutationFn: requestValuation, retry: false });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (valuation.isPending) return;

    valuation.reset();
    const latitude = Number(lat);
    const longitude = Number(lng);
    const areaSqm = area === "" ? undefined : Number(area);
    if (
      !lat.trim() ||
      !lng.trim() ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      Math.abs(latitude) > 90 ||
      Math.abs(longitude) > 180
    ) {
      setError("Enter a valid latitude and longitude.");
      return;
    }
    if (areaSqm !== undefined && (!Number.isFinite(areaSqm) || areaSqm <= 0)) {
      setError("Floor area must be greater than zero.");
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
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Location assessment"
        intro="Use coordinates for an area reference. Add floor area and room count for a property assessment."
      />
      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <form onSubmit={submit} className="card-surface space-y-3 p-5" noValidate>
          <fieldset className="grid grid-cols-2 gap-3">
            <legend className="mb-2 text-sm font-bold">Location (required)</legend>
            <label className="text-xs font-semibold">
              Latitude
              <input
                className={field}
                inputMode="decimal"
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                required
              />
            </label>
            <label className="text-xs font-semibold">
              Longitude
              <input
                className={field}
                inputMode="decimal"
                value={lng}
                onChange={(e) => setLng(e.target.value)}
                required
              />
            </label>
          </fieldset>
          <fieldset className="grid grid-cols-2 gap-3">
            <legend className="mb-2 text-sm font-bold">Apartment (optional)</legend>
            <label className="text-xs font-semibold">
              Rooms
              <select className={field} value={rooms} onChange={(e) => setRooms(e.target.value)}>
                <option value="">—</option>
                <option>1</option>
                <option>2</option>
                <option>3</option>
                <option>4</option>
              </select>
            </label>
            <label className="text-xs font-semibold">
              Floor area (m²)
              <input
                className={field}
                type="number"
                min={0}
                step="any"
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </label>
          </fieldset>
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

        <section aria-live="polite" className="space-y-4">
          {valuation.isPending && <p role="status">Loading market evidence…</p>}
          {!valuation.data && !valuation.isPending && !valuation.error && !error && (
            <div className="card-surface p-6 text-sm text-muted-foreground">
              Results will appear here.
            </div>
          )}
          {valuation.data && statistics && (
            <>
              <MarketAssessment estimate={valuation.data} />
              <section className="card-surface p-5" aria-labelledby="observed-rents-title">
                <h2 id="observed-rents-title" className="text-lg font-semibold">
                  Observed rents
                </h2>
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt>Mean monthly rent</dt>
                    <dd>
                      {statistics.cluster_mean_price_usd === null ? (
                        "Not available"
                      ) : (
                        <Money usd={statistics.cluster_mean_price_usd} suffix="/ month" />
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Monthly rent standard deviation</dt>
                    <dd>
                      {statistics.observed_price_std_dev_usd === null ? (
                        "Not available"
                      ) : (
                        <Money usd={statistics.observed_price_std_dev_usd} suffix="/ month" />
                      )}
                    </dd>
                  </div>
                </dl>
              </section>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
