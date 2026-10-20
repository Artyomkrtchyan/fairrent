import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader, RateNote } from "@/components/ui-bits";
import { TREND_DISTRICTS, WEEKLY_TRENDS } from "@/lib/data";
import { usePrefs } from "@/lib/prefs";

export const Route = createFileRoute("/analytics")({
  head: () => ({
    meta: [
      { title: "Yerevan rent trends by neighborhood — FairRent" },
      {
        name: "description",
        content:
          "Weekly median asking rents for Yerevan neighborhoods, with gaps where no data was observed. Synthetic demo.",
      },
      { property: "og:title", content: "Yerevan rent trends by neighborhood — FairRent" },
      {
        property: "og:description",
        content: "Weekly neighborhood asking-price trends. Synthetic demo data.",
      },
    ],
  }),
  component: Analytics,
});

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

function Analytics() {
  const { format, currency } = usePrefs();
  const [mode, setMode] = useState<"chart" | "table">("chart");
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Market analytics"
        intro="Weekly median asking rent for long-term listings. Weeks with no observations are shown as gaps — never as zero."
      />
      <div
        role="group"
        aria-label="Display as"
        className="mb-4 inline-flex rounded-md border p-0.5 text-xs font-semibold"
      >
        {(["chart", "table"] as const).map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mode === m}
            onClick={() => setMode(m)}
            className={`rounded px-3 py-1 capitalize ${mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}
          >
            {m}
          </button>
        ))}
      </div>

      {mode === "chart" ? (
        <figure className="card-surface p-4">
          <figcaption className="mb-2 text-sm font-semibold">
            Median asking rent per week ({currency}/month)
          </figcaption>
          <div className="h-[380px]" aria-hidden>
            {mounted && (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={WEEKLY_TRENDS} margin={{ left: 8, right: 16, top: 8 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="week"
                    tickFormatter={(w: string) => w.slice(5)}
                    stroke="var(--muted-foreground)"
                    fontSize={12}
                  />
                  <YAxis
                    tickFormatter={(v: number) => format(v)}
                    stroke="var(--muted-foreground)"
                    fontSize={12}
                    width={currency === "AMD" ? 90 : 60}
                  />
                  <Tooltip
                    formatter={(v) => (v == null ? "No data" : format(Number(v)))}
                    contentStyle={{
                      background: "var(--popover)",
                      border: "1px solid var(--border)",
                      color: "var(--popover-foreground)",
                    }}
                  />
                  <Legend />
                  {TREND_DISTRICTS.map((d, i) => (
                    <Line
                      key={d}
                      type="monotone"
                      dataKey={d}
                      stroke={COLORS[i] ?? "var(--chart-1)"}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Breaks in a line mean no listings were observed that week. Switch to Table for an
            accessible view.
          </p>
        </figure>
      ) : (
        <div className="card-surface overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="p-3 text-left font-semibold">
              Median asking rent per week ({currency}/month)
            </caption>
            <thead className="bg-muted text-left">
              <tr>
                <th scope="col" className="px-3 py-2">
                  Week starting
                </th>
                {TREND_DISTRICTS.map((d) => (
                  <th key={d} scope="col" className="px-3 py-2 text-right">
                    {d}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {WEEKLY_TRENDS.map((r) => (
                <tr key={r.week} className="border-t">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    {r.week}
                  </th>
                  {TREND_DISTRICTS.map((d) => (
                    <td key={d} className="px-3 py-2 text-right tabular-nums">
                      {r[d] == null ? (
                        <span className="text-muted-foreground">No data</span>
                      ) : (
                        format(r[d]!)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-3">
        <RateNote />
      </div>
    </main>
  );
}
