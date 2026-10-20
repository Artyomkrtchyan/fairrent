import { createFileRoute } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Money, PageHeader, RateNote } from "@/components/ui-bits";
import { assessLocation, YEREVAN_BOUNDS, type AreaAssessment } from "@/lib/data";

export const Route = createFileRoute("/valuation")({
  head: () => ({
    meta: [
      { title: "Location rent assessment — FairRent" },
      {
        name: "description",
        content:
          "Get an area rent reference for Yerevan coordinates, optionally refined with apartment details. Synthetic demo.",
      },
      { property: "og:title", content: "Location rent assessment — FairRent" },
      {
        property: "og:description",
        content: "Area reference rents for a Yerevan location. Synthetic demo data.",
      },
    ],
  }),
  component: Valuation,
});

const field = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm";

function Valuation() {
  const [lat, setLat] = useState("40.1872");
  const [lng, setLng] = useState("44.5152");
  const [rooms, setRooms] = useState("");
  const [area, setArea] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<(AreaAssessment & { withArea: boolean }) | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const la = Number(lat),
      ln = Number(lng),
      b = YEREVAN_BOUNDS;
    if (
      !lat ||
      !lng ||
      Number.isNaN(la) ||
      Number.isNaN(ln) ||
      la < b.latMin ||
      la > b.latMax ||
      ln < b.lngMin ||
      ln > b.lngMax
    ) {
      setError(
        `Enter coordinates inside Yerevan (latitude ${b.latMin}–${b.latMax}, longitude ${b.lngMin}–${b.lngMax}).`,
      );
      setRes(null);
      return;
    }
    setError(null);
    setRes({
      ...assessLocation(la, ln, area ? +area : undefined, rooms ? +rooms : undefined),
      withArea: !!area,
    });
  };

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Location assessment"
        intro="Coordinates alone give an area reference — typical rents nearby — not a valuation of a specific apartment. Add floor area for a property-specific indicative range."
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
                min={10}
                max={500}
                value={area}
                onChange={(e) => setArea(e.target.value)}
              />
            </label>
          </fieldset>
          {error && (
            <p role="alert" className="text-sm font-semibold text-destructive">
              {error}
            </p>
          )}
          <button className="w-full rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90">
            Assess location
          </button>
        </form>

        <section aria-live="polite" className="space-y-4">
          {!res && (
            <div className="card-surface p-6 text-sm text-muted-foreground">
              Results will appear here.
            </div>
          )}
          {res && (
            <>
              <div className="card-surface p-5">
                <p className="text-xs font-bold uppercase text-muted-foreground">
                  Area reference · not a valuation
                </p>
                <h2 className="mt-1 text-xl font-semibold">
                  Typical rents within {res.radiusKm} km
                </h2>
                {res.sampleSize === 0 ? (
                  <p className="mt-2 text-sm">
                    No synthetic listings near this point — no reference available.
                  </p>
                ) : (
                  <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
                    <div>
                      <dt className="text-xs text-muted-foreground">Sample size</dt>
                      <dd className="text-xl font-bold text-heading">{res.sampleSize}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">Median rent</dt>
                      <dd className="font-bold">
                        {res.medianRentUsd && <Money usd={res.medianRentUsd} />}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted-foreground">Median per m²</dt>
                      <dd className="font-bold">
                        {res.medianPerM2Usd && <Money usd={res.medianPerM2Usd} suffix="/m²" />}
                      </dd>
                    </div>
                  </dl>
                )}
                {res.sampleSize > 0 && res.sampleSize < 5 && (
                  <p className="mt-2 text-xs font-semibold text-above">
                    Small sample — treat with caution.
                  </p>
                )}
              </div>
              <div className="card-surface p-5">
                <p className="text-xs font-bold uppercase text-muted-foreground">
                  Property-specific assessment
                </p>
                {res.property ? (
                  <>
                    <p className="mt-1 text-2xl font-bold text-heading">
                      <Money usd={res.property.interval[0]} suffix="" /> –{" "}
                      <Money usd={res.property.interval[1]} />
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Indicative range from area median per m² × your floor area. Condition, floor
                      and building quality are not accounted for.
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-sm">
                    {res.withArea
                      ? "Too few comparable listings nearby for a property-specific range."
                      : "Add floor area to get an indicative range for a specific apartment. Coordinates alone cannot value a property."}
                  </p>
                )}
              </div>
              <RateNote />
              <p className="text-xs text-muted-foreground">
                Computed from synthetic demo listings only.
              </p>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
