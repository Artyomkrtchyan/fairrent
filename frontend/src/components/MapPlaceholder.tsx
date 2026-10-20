import { Link } from "@tanstack/react-router";
import { priceStatus, YEREVAN_BOUNDS, type Listing } from "@/lib/data";
import { cn } from "@/lib/utils";

const DOT: Record<string, string> = {
  within: "fill-within",
  above: "fill-above",
  below: "fill-below",
  unavailable: "fill-neutral",
};

function project(lat: number, lng: number) {
  const b = YEREVAN_BOUNDS;
  return {
    x: ((lng - b.lngMin) / (b.lngMax - b.lngMin)) * 400,
    y: (1 - (lat - b.latMin) / (b.latMax - b.latMin)) * 400,
  };
}

/** Schematic placeholder — the interactive Leaflet map is deferred. */
export function MapPlaceholder({
  listings,
  highlight,
  className,
}: {
  listings: Listing[];
  highlight?: string | null;
  className?: string;
}) {
  return (
    <div className={cn("card-surface relative flex h-full flex-col overflow-hidden", className)}>
      <div className="flex items-center justify-between border-b px-4 py-2 text-xs">
        <span className="font-semibold text-heading">Schematic map · not to scale</span>
        <span className="text-muted-foreground">Interactive map coming later</span>
      </div>
      <svg
        viewBox="0 0 400 400"
        className="min-h-0 w-full flex-1 bg-map-land"
        role="group"
        aria-label={`Schematic map of Yerevan showing ${listings.length} listings`}
      >
        <path
          d="M60 330 C120 300 150 260 170 220 S210 140 250 110 S320 60 360 40"
          className="stroke-map-river"
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
        />
        <text x="250" y="96" className="fill-muted-foreground" fontSize="10">
          Hrazdan river
        </text>
        {[
          ["Kentron", 236, 200],
          ["Arabkir", 214, 130],
          ["Davtashen", 160, 60],
          ["Nor Nork", 330, 150],
          ["Ajapnyak", 110, 140],
          ["Shengavit", 150, 290],
          ["Avan", 330, 70],
          ["Malatia", 90, 230],
        ].map(([n, x, y]) => (
          <text
            key={n as string}
            x={x as number}
            y={y as number}
            fontSize="11"
            textAnchor="middle"
            className="fill-muted-foreground font-semibold"
          >
            {n}
          </text>
        ))}
        {listings.map((l) => {
          const p = project(l.lat, l.lng);
          const on = highlight === l.id;
          return (
            <Link key={l.id} to="/listings/$id" params={{ id: l.id }} aria-label={l.title}>
              <circle
                cx={p.x}
                cy={p.y}
                r={on ? 10 : 7}
                className={cn(DOT[priceStatus(l)], "stroke-card")}
                strokeWidth="2"
                opacity={l.active ? 1 : 0.45}
              />
            </Link>
          );
        })}
      </svg>
      <ul className="flex flex-wrap gap-3 border-t px-4 py-2 text-xs text-muted-foreground">
        {(["within", "above", "below", "unavailable"] as const).map((s) => (
          <li key={s} className="flex items-center gap-1">
            <svg width="10" height="10" aria-hidden>
              <circle cx="5" cy="5" r="5" className={DOT[s]} />
            </svg>
            {s === "unavailable" ? "No estimate" : s.slice(0, 1).toUpperCase() + s.slice(1)}
          </li>
        ))}
      </ul>
    </div>
  );
}
