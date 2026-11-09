import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { apiMode } from "@/api/client";
import { getListings } from "@/api/listings";
import { usePrefs } from "@/lib/prefs";
import {
  buildDistrictSnapshot,
  snapshotMedian,
  uniqueActiveListings,
  type SnapshotListing,
  type SnapshotMeasure,
} from "@/lib/listing-snapshot";

const MAX_PAGES = 30;
const PAGE_SIZE = 100;
const field = "rounded-md border bg-card px-3 py-2 text-sm";

export function ListingSnapshotAnalytics() {
  const { format, currency } = usePrefs();
  const [measure, setMeasure] = useState<SnapshotMeasure>("month");
  const [view, setView] = useState<"chart" | "table">("chart");
  const [districtFilter, setDistrictFilter] = useState("all");
  const [includeStale, setIncludeStale] = useState(true);
  const query = useInfiniteQuery({
    queryKey: ["market-listing-snapshot", apiMode],
    initialPageParam: 1,
    queryFn: ({ pageParam, signal }) =>
      getListings(signal, { page: pageParam, page_size: PAGE_SIZE, status: "active", sort: "newest" }),
    getNextPageParam: (lastPage, pages) =>
      lastPage.has_more && pages.length < MAX_PAGES ? lastPage.page + 1 : undefined,
    retry: false,
    staleTime: 2 * 60 * 1000,
  });
  // Load the full available snapshot up to the documented 3,000-row safety cap.
  // The UI explicitly marks partial coverage if the API has more rows.
  useEffect(() => {
    if (query.hasNextPage && !query.isFetching && !query.isError) {
      void query.fetchNextPage();
    }
  }, [query.hasNextPage, query.isFetching, query.isError, query.fetchNextPage]);

  const records = useMemo(
    () => (query.data?.pages.flatMap((page) => page.items) ?? []) as SnapshotListing[],
    [query.data],
  );
  const unique = useMemo(() => uniqueActiveListings(records), [records]);
  const total = query.data?.pages[0]?.total ?? 0;
  const hasUnloaded = query.data?.pages.at(-1)?.has_more ?? false;
  const fullyLoaded = Boolean(query.data) && !hasUnloaded && !query.isError;
  const visibleRecords = useMemo(
    () => unique.filter((listing) => includeStale || !listing.freshness.is_stale),
    [unique, includeStale],
  );
  const districts = useMemo(() => buildDistrictSnapshot(visibleRecords), [visibleRecords]);
  const availableDistricts = useMemo(() => buildDistrictSnapshot(unique), [unique]);
  const filtered = useMemo(
    () => districtFilter === "all"
      ? visibleRecords
      : visibleRecords.filter((item) => item.district_id === districtFilter),
    [visibleRecords, districtFilter],
  );
  const shownDistricts = districtFilter === "all"
    ? districts
    : districts.filter((item) => item.districtId === districtFilter);
  const selectedMedian = snapshotMedian(filtered, measure);
  const sampleCount = filtered.length;
  const dated = visibleRecords.map((item) => item.last_seen_at).filter(Boolean).sort();
  const lastObserved = dated.at(-1);
  const selectedUnit = measure === "month" ? `${currency}/month` : `${currency}/m²/month`;
  const metricValue = (district: (typeof districts)[number]) =>
    measure === "month" ? district.medianMonthlyUsd : district.medianPerSqmUsd;
  const metricCount = (district: (typeof districts)[number]) =>
    measure === "month" ? district.pricedCount : district.areaPricedCount;
  const chartData = shownDistricts
    .filter((district) => metricValue(district) !== null)
    .map((district) => ({ district: district.label, median: metricValue(district)!, count: metricCount(district) }))
    .sort((a, b) => b.median - a.median);

  return (
    <section className="space-y-5" aria-label="Current listing market snapshot">
      <div className="card-surface p-5">
        <h2 className="text-xl font-semibold">Current listing snapshot</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Compare asking rents in the active listings currently available from FairRent.
          This is a cross-sectional snapshot, not a weekly price trend or completed lease data.
          Each apartment is counted once where deduplication information is available.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 text-sm font-semibold">
            Neighborhood
            <select className={field} value={districtFilter} onChange={(event) => setDistrictFilter(event.target.value)}>
              <option value="all">All neighborhoods</option>
              {availableDistricts.map((district) => (
                <option key={district.districtId} value={district.districtId}>{district.label}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm font-semibold">
            Measure
            <select className={field} value={measure} onChange={(event) => setMeasure(event.target.value === "m2" ? "m2" : "month")}>
              <option value="month">Monthly asking rent</option>
              <option value="m2">Monthly asking rent per m²</option>
            </select>
          </label>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={includeStale} onChange={(event) => setIncludeStale(event.target.checked)} />
              Include stale listings
            </label>
          </div>
        </div>
      </div>

      {query.isPending && <p role="status" className="card-surface p-5">Loading actual rental listings…</p>}
      {query.isError && (
        <section role="alert" className="card-surface p-5">
          <h3 className="font-semibold">Could not load {query.isFetchNextPageError ? "the next listings page" : "current listings"}.</h3>
          <p className="mt-2 text-sm">Previously loaded pages remain available if any were retrieved. No synthetic values are substituted.</p>
          <button className="mt-3 rounded-md border px-4 py-2 text-sm" type="button"
            onClick={() => void (query.isFetchNextPageError ? query.fetchNextPage() : query.refetch())}>
            Retry
          </button>
        </section>
      )}

      {query.data && (
        <>
          {!fullyLoaded && (
            <p role="status" className="rounded-md border px-4 py-3 text-sm">
              <strong>Partial coverage:</strong> {records.length.toLocaleString()} of {total.toLocaleString()} API listing rows loaded.
              District figures currently describe only the loaded subset, not the whole market.
              {hasUnloaded && query.data.pages.length >= MAX_PAGES && " The 3,000-row request limit has been reached."}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card-surface p-4">
              <p className="text-xs text-muted-foreground">Active rental listings represented</p>
              <p className="mt-2 text-2xl font-bold">{sampleCount.toLocaleString()}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {districtFilter === "all" ? "All available neighborhoods" : "Selected neighborhood"}
                {includeStale ? "" : " · Excludes stale"}
              </p>
            </div>
            <div className="card-surface p-4">
              <p className="text-xs text-muted-foreground">Median asking rent ({selectedUnit})</p>
              <p className="mt-2 text-2xl font-bold">{selectedMedian === null ? "Unavailable" : format(selectedMedian)}</p>
              <p className="mt-1 text-xs text-muted-foreground">Calculated from listings with usable prices{measure === "m2" ? " and floor area" : ""}</p>
            </div>
            <div className="card-surface p-4">
              <p className="text-xs text-muted-foreground">Most recent listing observation</p>
              <p className="mt-2 text-lg font-semibold">
                {lastObserved ? new Date(lastObserved).toLocaleDateString("en-GB", { timeZone: "Asia/Yerevan" }) : "Unavailable"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">Not a time-series data point</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold">Neighborhood comparison</h2>
            <div role="group" aria-label="Display as" className="flex gap-2">
              {(["chart", "table"] as const).map((mode) => (
                <button
                  type="button" key={mode} aria-pressed={view === mode}
                  onClick={() => setView(mode)}
                  className="rounded-md border bg-card px-4 py-2 text-sm capitalize aria-pressed:border-primary aria-pressed:font-bold"
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
          {shownDistricts.length === 0 ? (
            <div className="card-surface p-5 text-sm">
              No matching listings with a known neighborhood. Try another selection or include stale listings.
            </div>
          ) : view === "chart" ? (
            <figure className="card-surface p-4">
              <figcaption className="mb-3 font-semibold">Median asking rent by neighborhood ({selectedUnit})</figcaption>
              {chartData.length ? (
                <div style={{ height: Math.max(270, chartData.length * 38 + 50) }} aria-hidden="true">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ left: 15, right: 28 }}>
                      <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                      <XAxis type="number" tickFormatter={(value: number) => format(value)} />
                      <YAxis dataKey="district" type="category" width={125} fontSize={12} />
                      <Tooltip
                        formatter={(value) => [format(Number(value)), "Median asking rent"]}
                        contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", color: "var(--popover-foreground)" }}
                      />
                      <Bar dataKey="median" name="Median rent" fill="var(--primary)" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="py-6 text-sm">Not enough listings with valid prices{measure === "m2" ? " and area" : ""} for this measure.</p>
              )}
              <p className="mt-2 text-xs text-muted-foreground">District medians reflect only the loaded active listing sample. No weekly price history is inferred.</p>
            </figure>
          ) : (
            <div className="card-surface overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="p-4 text-left font-semibold">Current asking-rent medians by neighborhood ({selectedUnit})</caption>
                <thead className="bg-muted"><tr>
                  <th scope="col" className="p-3">Neighborhood</th>
                  <th scope="col" className="p-3">Active listings</th>
                  <th scope="col" className="p-3">Usable observations</th>
                  <th scope="col" className="p-3">Median asking rent</th>
                </tr></thead>
                <tbody>{shownDistricts.map((district) => (
                  <tr key={district.districtId} className="border-t">
                    <th scope="row" className="p-3 font-medium">{district.label}</th>
                    <td className="p-3">{district.listingCount}</td>
                    <td className="p-3">{metricCount(district)}</td>
                    <td className="p-3">{metricValue(district) === null ? "Unavailable" : format(metricValue(district)!)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Loaded {records.length.toLocaleString()} of {total.toLocaleString()} active listing rows ({unique.length.toLocaleString()} unique after available deduplication).
            </p>
            {query.hasNextPage && (
              <button type="button" className="rounded-md border bg-card px-4 py-2 text-sm font-semibold"
                disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>
                {query.isFetchingNextPage ? "Loading…" : "Load more listings"}
              </button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Asking-price observations are not completed transactions or a representative survey.
            Unknown districts are excluded from the comparison. The market-index weekly pipeline
            remains a separate feature; an absent weekly dataset is never reconstructed from this snapshot.
          </p>
        </>
      )}
    </section>
  );
}
