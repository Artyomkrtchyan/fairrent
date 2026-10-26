import { createFileRoute } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiMode } from "@/api/client";
import { getMarketIndex } from "@/api/market";
import { PageHeader, RateNote } from "@/components/ui-bits";
import {
  buildMarketSeries,
  marketCount,
  marketValue,
  type MarketMeasure,
} from "@/lib/market-series";
import { usePrefs } from "@/lib/prefs";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [{ title: "Neighborhood rent trends — FairRent" }],
  }),
  component: MarketAnalytics,
});

const DISTRICTS = [
  ["ajapnyak", "Ajapnyak"],
  ["arabkir", "Arabkir"],
  ["avan", "Avan"],
  ["davtashen", "Davtashen"],
  ["erebuni", "Erebuni"],
  ["kanaker-zeytun", "Kanaker-Zeytun"],
  ["kentron", "Kentron"],
  ["malatia-sebastia", "Malatia-Sebastia"],
  ["nor-nork", "Nor Nork"],
  ["nork-marash", "Nork-Marash"],
  ["nubarashen", "Nubarashen"],
  ["shengavit", "Shengavit"],
] as const;

const INITIAL_FILTERS = {
  district_id: "kentron",
  period_start: "",
  period_end: "",
};

function observationDate(value: string | null) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleDateString("en-GB", {
    timeZone: "Asia/Yerevan",
  });
}

export function MarketAnalytics() {
  const { format, currency } = usePrefs();
  const [draft, setDraft] = useState(INITIAL_FILTERS);
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [measure, setMeasure] = useState<MarketMeasure>("month");
  const [view, setView] = useState<"chart" | "table">("chart");
  const [filterError, setFilterError] = useState("");

  const query = useInfiniteQuery({
    queryKey: ["market-index", apiMode, filters],
    initialPageParam: 1,
    queryFn: ({ signal, pageParam }) =>
      getMarketIndex(
        {
          district_id: filters.district_id,
          ...(filters.period_start ? { period_start: filters.period_start } : {}),
          ...(filters.period_end ? { period_end: filters.period_end } : {}),
          page: pageParam,
          page_size: 100,
        },
        signal,
      ),
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    retry: false,
  });

  const records = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const series = useMemo(() => buildMarketSeries(records, measure), [records, measure]);
  const latest = series.at(-1)?.record;
  const firstPage = query.data?.pages[0];
  const districtName =
    DISTRICTS.find(([id]) => id === filters.district_id)?.[1] ?? filters.district_id;
  const units = measure === "month" ? `${currency}/month` : `${currency}/month/m²`;
  const hasValues = records.some((record) => marketValue(record, measure) !== null);
  const fieldClass = "mt-1 w-full rounded-md border bg-card px-3 py-2";

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <PageHeader
        title="Market analytics"
        intro="Explore weekly median asking rents. These are advertised rents, not completed rental agreements."
        tag={apiMode === "mock"}
      />

      <form
        className="card-surface p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (draft.period_start && draft.period_end && draft.period_start > draft.period_end) {
            setFilterError("The start date must not be after the end date.");
            return;
          }
          setFilterError("");
          setFilters({ ...draft });
        }}
      >
        <div className="grid items-end gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm font-semibold">
            Neighborhood
            <select
              className={fieldClass}
              value={draft.district_id}
              onChange={(event) => setDraft({ ...draft, district_id: event.target.value })}
            >
              {DISTRICTS.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold">
            Week starting from
            <input
              type="date"
              className={fieldClass}
              value={draft.period_start}
              onChange={(event) => setDraft({ ...draft, period_start: event.target.value })}
            />
          </label>
          <label className="text-sm font-semibold">
            Week starting through
            <input
              type="date"
              className={fieldClass}
              value={draft.period_end}
              onChange={(event) => setDraft({ ...draft, period_end: event.target.value })}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 font-semibold text-primary-foreground"
            >
              Apply
            </button>
            <button
              type="button"
              className="rounded-md border px-4 py-2"
              onClick={() => {
                setDraft(INITIAL_FILTERS);
                setFilters(INITIAL_FILTERS);
                setFilterError("");
              }}
            >
              Reset
            </button>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Dates select weekly start dates. Leave them blank to explore the available history.
        </p>
        {filterError && (
          <p role="alert" className="mt-3 text-sm text-red-600">
            {filterError}
          </p>
        )}
      </form>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <label className="text-sm font-semibold">
          Measure
          <select
            className={fieldClass}
            value={measure}
            onChange={(event) => setMeasure(event.target.value === "m2" ? "m2" : "month")}
          >
            <option value="month">Monthly asking rent</option>
            <option value="m2">Monthly asking rent per m²</option>
          </select>
        </label>
        <div role="group" aria-label="Display as" className="flex gap-2">
          {(["chart", "table"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              aria-pressed={view === mode}
              onClick={() => setView(mode)}
              className="rounded-md border bg-card px-4 py-2 text-sm capitalize aria-pressed:border-primary aria-pressed:font-bold"
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {query.isPending && <p role="status">Loading market analytics…</p>}
      {query.isFetching && !query.isPending && <p role="status">Updating market analytics…</p>}
      {query.isError && (
        <section role="alert" className="card-surface p-5">
          <h2 className="font-sans font-bold">Could not load market analytics.</h2>
          <p className="mt-2 text-sm">
            {query.data
              ? "Previously loaded records remain below."
              : "Check the API connection and try again."}
          </p>
          <button
            type="button"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
            className="mt-3 rounded-md border px-4 py-2"
          >
            Retry
          </button>
        </section>
      )}

      {firstPage && (
        <section className="space-y-4" aria-label={`${districtName} market results`}>
          <div>
            <h2 className="text-2xl font-semibold">{districtName}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Available week starts: {firstPage.available_from ?? "None"} —{" "}
              {firstPage.available_to ?? "None"}
            </p>
          </div>

          {records.length === 0 ? (
            <div className="card-surface p-6">
              <h3 className="font-sans font-bold">No published weekly data for this selection.</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Try another neighborhood or date range. Missing data does not mean rents are zero.
              </p>
            </div>
          ) : (
            <>
              {latest && (
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="card-surface p-4">
                    <p className="text-xs text-muted-foreground">
                      Latest loaded weekly median ({units})
                    </p>
                    <p className="mt-2 text-xl font-bold">
                      {marketValue(latest, measure) === null
                        ? "Unavailable"
                        : format(marketValue(latest, measure)!)}
                    </p>
                    <p className="mt-1 text-xs">
                      {latest.period_start} — {latest.period_end}
                    </p>
                  </div>
                  <div className="card-surface p-4">
                    <p className="text-xs text-muted-foreground">
                      Observations for this measure and week
                    </p>
                    <p className="mt-2 text-xl font-bold">{marketCount(latest, measure)}</p>
                  </div>
                  <div className="card-surface p-4">
                    <p className="text-xs text-muted-foreground">Source observed through</p>
                    <p className="mt-2 font-bold">{observationDate(latest.data_as_of)}</p>
                    <p className="mt-1 text-xs">
                      {latest.freshness.is_stale
                        ? "Source data is stale"
                        : "Within the API freshness window"}
                    </p>
                  </div>
                </div>
              )}

              {view === "chart" ? (
                <figure className="card-surface p-4">
                  <figcaption className="mb-4 font-semibold">
                    Weekly median asking rent ({units})
                  </figcaption>
                  {hasValues ? (
                    <div className="h-[360px]" aria-hidden="true">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={series} margin={{ left: 8, right: 20, top: 12 }}>
                          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                          <XAxis
                            dataKey="timestamp"
                            type="number"
                            scale="time"
                            domain={["dataMin", "dataMax"]}
                            tickFormatter={(value: number) =>
                              new Date(value).toISOString().slice(5, 10)
                            }
                            stroke="var(--muted-foreground)"
                            fontSize={12}
                          />
                          <YAxis
                            tickFormatter={(value: number) => format(value)}
                            width={110}
                            stroke="var(--muted-foreground)"
                            fontSize={11}
                          />
                          <Tooltip
                            labelFormatter={(value) =>
                              new Date(Number(value)).toISOString().slice(0, 10)
                            }
                            formatter={(value) =>
                              value == null ? "Unavailable" : format(Number(value))
                            }
                            contentStyle={{
                              background: "var(--popover)",
                              border: "1px solid var(--border)",
                              color: "var(--popover-foreground)",
                            }}
                          />
                          <Line
                            type="linear"
                            dataKey="value"
                            name="Weekly median"
                            stroke="var(--primary)"
                            strokeWidth={2}
                            dot={{ r: 4 }}
                            connectNulls={false}
                            isAnimationActive={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="py-8 text-sm">
                      Values for this measure are unavailable. The table still shows observation
                      counts.
                    </p>
                  )}
                  <p className="mt-3 text-xs text-muted-foreground">
                    Gaps represent missing or unavailable weekly values. Switch to Table for values,
                    counts and freshness.
                  </p>
                </figure>
              ) : (
                <div className="card-surface overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <caption className="p-4 text-left font-semibold">
                      Weekly median asking rent ({units})
                    </caption>
                    <thead className="bg-muted">
                      <tr>
                        <th scope="col" className="p-3">
                          Period
                        </th>
                        <th scope="col" className="p-3">
                          Median
                        </th>
                        <th scope="col" className="p-3">
                          Observations
                        </th>
                        <th scope="col" className="p-3">
                          Source observed through
                        </th>
                        <th scope="col" className="p-3">
                          Freshness
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((record) => (
                        <tr
                          key={`${record.district_id}-${record.period_start}`}
                          className="border-t"
                        >
                          <th scope="row" className="whitespace-nowrap p-3 font-medium">
                            {record.period_start} — {record.period_end}
                          </th>
                          <td className="whitespace-nowrap p-3">
                            {marketValue(record, measure) === null
                              ? "Unavailable"
                              : format(marketValue(record, measure)!)}
                          </td>
                          <td className="p-3">{marketCount(record, measure)}</td>
                          <td className="whitespace-nowrap p-3">
                            {observationDate(record.data_as_of)}
                          </td>
                          <td className="p-3">
                            {record.freshness.is_stale ? "Stale" : "Within freshness window"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">
              {records.length} of {firstPage.total} weekly records loaded.
            </p>
            {query.hasNextPage && (
              <button
                type="button"
                disabled={query.isFetching}
                onClick={() => void query.fetchNextPage()}
                className="rounded-md border bg-card px-4 py-2 text-sm font-semibold"
              >
                {query.isFetchingNextPage ? "Loading…" : "Load more weeks"}
              </button>
            )}
          </div>
        </section>
      )}
      <RateNote />
    </main>
  );
}
