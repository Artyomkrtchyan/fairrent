import { useState, type FormEvent } from "react";
import Decimal from "decimal.js-light";

import { usePrefs } from "@/lib/prefs";
import type { CatalogueSearch } from "@/lib/catalogue-search";

interface Props {
  search: CatalogueSearch;
  onApply: (search: CatalogueSearch) => void;
}

const inputClass = "mt-1 w-full rounded-md border bg-card px-3 py-2 text-sm";

export function CatalogueFilters({ search, onApply }: Props) {
  const { currency, amdPerUsd } = usePrefs();

  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  const [district, setDistrict] = useState(search.district_id ?? "");
  const [rooms, setRooms] = useState(search.rooms?.toString() ?? "");
  const [priceMin, setPriceMin] = useState(search.price_min?.toString() ?? "");
  const [priceMax, setPriceMax] = useState(search.price_max?.toString() ?? "");
  const [areaMin, setAreaMin] = useState(search.area_min?.toString() ?? "");
  const [areaMax, setAreaMax] = useState(search.area_max?.toString() ?? "");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const fields = [priceMin, priceMax, rooms, areaMin, areaMax];

    if (fields.some((value) => value !== "" && !Number.isFinite(Number(value)))) {
      setError("Please enter valid numbers.");
      return;
    }

    if ((priceMin !== "" && Number(priceMin) < 0) || (priceMax !== "" && Number(priceMax) < 0)) {
      setError("Rent cannot be negative.");
      return;
    }

    if (rooms !== "" && (!Number.isSafeInteger(Number(rooms)) || Number(rooms) < 1)) {
      setError("Rooms must be a whole number of at least 1.");
      return;
    }

    if ((areaMin !== "" && Number(areaMin) <= 0) || (areaMax !== "" && Number(areaMax) <= 0)) {
      setError("Area must be greater than zero.");
      return;
    }

    if (priceMin !== "" && priceMax !== "" && Number(priceMin) > Number(priceMax)) {
      setError("Minimum rent cannot exceed maximum rent.");
      return;
    }

    if (areaMin !== "" && areaMax !== "" && Number(areaMin) > Number(areaMax)) {
      setError("Minimum area cannot exceed maximum area.");
      return;
    }

    const next: CatalogueSearch = {
      page: 1,
      page_size: search.page_size,
      sort: search.sort,
      status: search.status,
    };

    if (search.bbox) next.bbox = search.bbox;

    if (district.trim()) {
      next.district_id = district.trim();
    }

    if (rooms !== "") next.rooms = Number(rooms);
    if (priceMin !== "") next.price_min = Number(priceMin);
    if (priceMax !== "") next.price_max = Number(priceMax);
    if (areaMin !== "") next.area_min = Number(areaMin);
    if (areaMax !== "") next.area_max = Number(areaMax);

    onApply(next);
  }

  return (
    <section className="card-surface relative p-4 shadow-lg">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-sans text-base font-bold">Find your rental</h2>

        <button
          type="button"
          aria-expanded={open}
          aria-controls="catalogue-filter-fields"
          onClick={() => setOpen((value) => !value)}
          className="rounded-md border px-3 py-2 text-sm md:hidden"
        >
          {open ? "Hide filters" : "Show filters"}
        </button>
      </div>

      <form onSubmit={submit}>
        <div
          id="catalogue-filter-fields"
          className={`${open ? "grid" : "hidden"} mt-4 gap-4 md:grid md:grid-cols-2 xl:grid-cols-4`}
        >
          <label className="text-sm font-semibold">
            District
            <input
              className={inputClass}
              list="catalogue-districts"
              value={district}
              onChange={(event) => setDistrict(event.target.value)}
              placeholder="All districts"
            />
            <datalist id="catalogue-districts">
              <option value="kentron">Kentron</option>
              <option value="arabkir">Arabkir</option>
            </datalist>
          </label>

          <label className="text-sm font-semibold">
            Exact rooms
            <input
              className={inputClass}
              type="number"
              min="1"
              step="1"
              value={rooms}
              onChange={(event) => setRooms(event.target.value)}
              placeholder="Any"
            />
          </label>

          <RentField
            key={`min-${currency}-${amdPerUsd}`}
            label={`Minimum rent (${currency}/month)`}
            canonicalUsd={priceMin}
            boundary="minimum"
            onChange={setPriceMin}
          />

          <RentField
            key={`max-${currency}-${amdPerUsd}`}
            label={`Maximum rent (${currency}/month)`}
            canonicalUsd={priceMax}
            boundary="maximum"
            onChange={setPriceMax}
          />

          <label className="text-sm font-semibold">
            Minimum area (m²)
            <input
              className={inputClass}
              type="number"
              min="0.01"
              step="any"
              value={areaMin}
              onChange={(event) => setAreaMin(event.target.value)}
              placeholder="No minimum"
            />
          </label>

          <label className="text-sm font-semibold">
            Maximum area (m²)
            <input
              className={inputClass}
              type="number"
              min="0.01"
              step="any"
              value={areaMax}
              onChange={(event) => setAreaMax(event.target.value)}
              placeholder="No maximum"
            />
          </label>

          <div className="flex flex-wrap items-end gap-2 xl:col-span-2">
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
            >
              Apply filters
            </button>

            <button
              type="button"
              onClick={() =>
                onApply({
                  page: 1,
                  page_size: search.page_size,
                  sort: search.sort,
                  status: "active",
                })
              }
              className="rounded-md border px-4 py-2 text-sm font-semibold"
            >
              Clear all
            </button>
          </div>
        </div>

        {error && (
          <p role="alert" className="mt-3 text-sm text-red-600 dark:text-red-300">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

interface RentFieldProps {
  label: string;
  canonicalUsd: string;
  boundary: "minimum" | "maximum";
  onChange: (usd: string) => void;
}

function RentField({ label, canonicalUsd, boundary, onChange }: RentFieldProps) {
  const { currency, amdPerUsd } = usePrefs();

  const [display, setDisplay] = useState(() => {
    if (canonicalUsd === "") return "";

    if (currency === "AMD" && amdPerUsd !== null) {
      return new Decimal(canonicalUsd).times(amdPerUsd).toFixed(0, Decimal.ROUND_HALF_UP);
    }

    return canonicalUsd;
  });

  function update(value: string) {
    setDisplay(value);

    if (value === "") {
      onChange("");
      return;
    }

    if (!Number.isFinite(Number(value))) {
      onChange(value);
      return;
    }

    if (currency === "AMD" && amdPerUsd !== null) {
      onChange(
        new Decimal(value)
          .dividedBy(amdPerUsd)
          .toFixed(2, boundary === "minimum" ? Decimal.ROUND_FLOOR : Decimal.ROUND_CEIL),
      );
      return;
    }

    onChange(value);
  }

  return (
    <label className="text-sm font-semibold">
      {label}
      <input
        className={inputClass}
        type="number"
        min="0"
        step="any"
        value={display}
        onChange={(event) => update(event.target.value)}
        placeholder={boundary === "minimum" ? "No minimum" : "No maximum"}
      />
    </label>
  );
}
