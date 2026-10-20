import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { usePrefs, type ThemePref } from "@/lib/prefs";

const NAV = [
  { to: "/", label: "Browse" },
  { to: "/valuation", label: "Location assessment" },
  { to: "/analytics", label: "Market analytics" },
  { to: "/reviews", label: "Reviewer preview" },
] as const;

export function SiteHeader() {
  const { theme, setTheme, currency, setCurrency, canUseAmd, rateLoading } = usePrefs();

  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b bg-card/95 backdrop-blur">
      <div className="mx-auto grid max-w-7xl grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 sm:px-6 lg:flex lg:justify-between">
        <Link to="/" className="flex min-w-0 items-center gap-2">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-hero font-display text-lg font-bold text-hero-foreground">
            F
          </span>

          <span className="truncate font-display text-xl font-semibold text-heading">FairRent</span>

          <span className="hidden text-xs text-muted-foreground sm:inline">
            Yerevan long-term rentals
          </span>
        </Link>

        <nav aria-label="Main" className="hidden lg:block">
          <ul className="flex gap-1">
            {NAV.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  activeOptions={{ exact: item.to === "/" }}
                  className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground data-[status=active]:bg-accent data-[status=active]:text-accent-foreground"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="Display currency"
            className="flex rounded-md border p-0.5 text-xs font-semibold"
          >
            <button
              type="button"
              aria-pressed={currency === "USD"}
              onClick={() => setCurrency("USD")}
              className={`rounded px-2 py-1 ${
                currency === "USD" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
              }`}
            >
              USD
            </button>

            <button
              type="button"
              disabled={!canUseAmd}
              aria-pressed={currency === "AMD"}
              onClick={() => setCurrency("AMD")}
              title={
                canUseAmd
                  ? "Show amounts in Armenian dram"
                  : rateLoading
                    ? "Loading exchange rate"
                    : "AMD unavailable: no usable fresh exchange rate"
              }
              className={`rounded px-2 py-1 disabled:cursor-not-allowed disabled:opacity-50 ${
                currency === "AMD" ? "bg-primary text-primary-foreground" : "text-muted-foreground"
              }`}
            >
              AMD
            </button>
          </div>

          <label className="sr-only" htmlFor="theme-select">
            Theme
          </label>

          <select
            id="theme-select"
            value={theme}
            onChange={(event) => setTheme(event.target.value as ThemePref)}
            className="rounded-md border bg-card px-2 py-1.5 text-xs"
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>

          <button
            type="button"
            className="rounded-md border px-2 py-1.5 text-xs font-semibold lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            Menu
          </button>
        </div>
      </div>

      {open && (
        <nav id="mobile-nav" aria-label="Main mobile" className="border-t lg:hidden">
          <ul className="mx-auto max-w-7xl px-4 py-2">
            {NAV.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  onClick={() => setOpen(false)}
                  activeOptions={{ exact: item.to === "/" }}
                  className="block rounded-md px-3 py-2 text-sm font-medium data-[status=active]:bg-accent"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="mt-16 border-t bg-card">
      <div className="mx-auto max-w-7xl space-y-1 px-4 py-6 text-xs text-muted-foreground sm:px-6">
        <p>
          <strong className="text-foreground">FairRent.</strong> Long-term apartments in Yerevan.
          Preview screens may contain synthetic examples; these are not live listings or measured
          model results.
        </p>

        <p>
          Price comparisons are statistical estimates, not appraisals. A high asking rent alone does
          not establish fraud.
        </p>
      </div>
    </footer>
  );
}
