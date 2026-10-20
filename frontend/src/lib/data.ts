// All data in this file is SYNTHETIC demo data. Prices are canonical USD / month.
// Long-term rentals only — daily rentals are excluded by design.

export type PriceStatus = "within" | "above" | "below" | "unavailable";

export interface Listing {
  id: string;
  title: string;
  district: string;
  street: string;
  /** Demo photo key resolved in src/lib/photos.ts; null = show "Photo unavailable" placeholder. */
  thumbnailUrl: string | null;
  lat: number;
  lng: number;
  rooms: number;
  areaM2: number;
  floor: string;
  askingUsd: number;
  estimateUsd: number | null;
  interval: [number, number] | null; // calibrated 80% prediction interval
  comparables: number;
  sourceUpdated: string; // ISO date
  active: boolean;
  risks: string[];
  explanation: string;
}

export const SYNTHETIC_AMD_PER_USD = 388; // simulated demo rate — not live, not official

export const YEREVAN_BOUNDS = { latMin: 40.06, latMax: 40.25, lngMin: 44.4, lngMax: 44.65 };

export function priceStatus(l: Pick<Listing, "askingUsd" | "interval">): PriceStatus {
  if (!l.interval) return "unavailable";
  const [lo, hi] = l.interval;
  if (l.askingUsd > hi) return "above";
  if (l.askingUsd < lo) return "below";
  return "within";
}

export const STATUS_LABEL: Record<PriceStatus, string> = {
  within: "Within estimated range",
  above: "Above estimated range",
  below: "Below estimated range",
  unavailable: "Estimate unavailable",
};

export const DISTRICTS = [
  "Kentron",
  "Arabkir",
  "Davtashen",
  "Nor Nork",
  "Ajapnyak",
  "Shengavit",
  "Avan",
  "Malatia-Sebastia",
];

export const LISTINGS: Listing[] = [
  {
    id: "fr-1001",
    title: "Bright 2-room near Cascade",
    district: "Kentron",
    street: "Tamanyan St",
    thumbnailUrl: "demo-cascade",
    lat: 40.1906,
    lng: 44.5152,
    rooms: 2,
    areaM2: 68,
    floor: "5 / 9",
    askingUsd: 950,
    estimateUsd: 900,
    interval: [810, 1000],
    comparables: 42,
    sourceUpdated: "2026-10-17",
    active: true,
    risks: [],
    explanation:
      "Asking rent sits inside the estimated range for 2-room flats of similar size in central Kentron. Renovation level and proximity to Cascade push the estimate up.",
  },
  {
    id: "fr-1002",
    title: "Renovated 3-room, Northern Ave",
    district: "Kentron",
    street: "Northern Avenue",
    thumbnailUrl: "demo-premium",
    lat: 40.1835,
    lng: 44.5148,
    rooms: 3,
    areaM2: 105,
    floor: "7 / 12",
    askingUsd: 2100,
    estimateUsd: 1550,
    interval: [1380, 1740],
    comparables: 31,
    sourceUpdated: "2026-10-16",
    active: true,
    risks: [
      "Price is notably above comparable listings — this alone is not a sign of fraud.",
      "Listing photos reused in 1 other listing (synthetic signal).",
    ],
    explanation:
      "Asking rent is above the estimated range. Premium buildings on Northern Avenue often ask more; the model may not capture concierge or parking extras.",
  },
  {
    id: "fr-1003",
    title: "Quiet 1-room in Arabkir",
    district: "Arabkir",
    street: "Komitas Ave",
    thumbnailUrl: "demo-panel",
    lat: 40.2052,
    lng: 44.5031,
    rooms: 1,
    areaM2: 42,
    floor: "3 / 5",
    askingUsd: 420,
    estimateUsd: 470,
    interval: [430, 520],
    comparables: 57,
    sourceUpdated: "2026-10-18",
    active: true,
    risks: [],
    explanation:
      "Asking rent is slightly below the estimated range. Older interior finishes and no elevator likely explain the lower ask.",
  },
  {
    id: "fr-1004",
    title: "Family 3-room with balcony",
    district: "Arabkir",
    street: "Baghramyan Ave",
    thumbnailUrl: "demo-premium",
    lat: 40.1985,
    lng: 44.4995,
    rooms: 3,
    areaM2: 92,
    floor: "4 / 10",
    askingUsd: 1100,
    estimateUsd: 1080,
    interval: [960, 1200],
    comparables: 38,
    sourceUpdated: "2026-10-15",
    active: true,
    risks: [],
    explanation: "Asking rent matches comparable 3-room flats in Arabkir with similar floor area.",
  },
  {
    id: "fr-1005",
    title: "Studio near Davtashen bridge",
    district: "Davtashen",
    street: "Davtashen 3rd district",
    thumbnailUrl: "demo-panel",
    lat: 40.2265,
    lng: 44.4904,
    rooms: 1,
    areaM2: 35,
    floor: "8 / 14",
    askingUsd: 330,
    estimateUsd: 340,
    interval: [300, 380],
    comparables: 24,
    sourceUpdated: "2026-10-12",
    active: true,
    risks: [],
    explanation:
      "Within range for small flats in Davtashen, where rents are lower than the centre.",
  },
  {
    id: "fr-1006",
    title: "2-room in Nor Nork, new build",
    district: "Nor Nork",
    street: "Gai Ave",
    thumbnailUrl: "demo-panel",
    lat: 40.1962,
    lng: 44.5722,
    rooms: 2,
    areaM2: 64,
    floor: "11 / 16",
    askingUsd: 560,
    estimateUsd: null,
    interval: null,
    comparables: 6,
    sourceUpdated: "2026-10-09",
    active: true,
    risks: ["Too few comparable listings for a calibrated estimate."],
    explanation: "Not enough comparable new-build listings nearby to produce a reliable estimate.",
  },
  {
    id: "fr-1007",
    title: "Spacious 4-room, Ajapnyak",
    district: "Ajapnyak",
    street: "Halabyan St",
    thumbnailUrl: null,
    lat: 40.1985,
    lng: 44.4721,
    rooms: 4,
    areaM2: 118,
    floor: "2 / 9",
    askingUsd: 900,
    estimateUsd: 980,
    interval: [880, 1090],
    comparables: 19,
    sourceUpdated: "2026-10-14",
    active: true,
    risks: [],
    explanation: "Within range. Large flats in Ajapnyak cost less per m² than central districts.",
  },
  {
    id: "fr-1008",
    title: "1-room near Shengavit metro",
    district: "Shengavit",
    street: "Bagratunyats Ave",
    thumbnailUrl: null,
    lat: 40.1555,
    lng: 44.4943,
    rooms: 1,
    areaM2: 40,
    floor: "6 / 9",
    askingUsd: 290,
    estimateUsd: 360,
    interval: [320, 400],
    comparables: 33,
    sourceUpdated: "2026-10-11",
    active: true,
    risks: [
      "Asking rent below range — confirm the listing terms (deposit, utilities) before paying anything.",
    ],
    explanation:
      "Below the estimated range. Unusually low asks can be legitimate but are worth verifying in person.",
  },
  {
    id: "fr-1009",
    title: "2-room in Avan with view",
    district: "Avan",
    street: "Isahakyan St",
    thumbnailUrl: null,
    lat: 40.2202,
    lng: 44.5725,
    rooms: 2,
    areaM2: 58,
    floor: "9 / 9",
    askingUsd: 430,
    estimateUsd: 440,
    interval: [390, 490],
    comparables: 15,
    sourceUpdated: "2026-09-28",
    active: false,
    risks: [],
    explanation: "Within range at the time of last observation. This listing is no longer active.",
  },
  {
    id: "fr-1010",
    title: "3-room in Malatia-Sebastia",
    district: "Malatia-Sebastia",
    street: "Sebastia St",
    thumbnailUrl: "demo-panel",
    lat: 40.1702,
    lng: 44.4555,
    rooms: 3,
    areaM2: 80,
    floor: "5 / 9",
    askingUsd: 520,
    estimateUsd: 560,
    interval: [500, 620],
    comparables: 27,
    sourceUpdated: "2026-10-13",
    active: true,
    risks: [],
    explanation: "Within range for western Yerevan 3-room flats.",
  },
  {
    id: "fr-1011",
    title: "Designer loft, Kentron",
    district: "Kentron",
    street: "Pushkin St",
    thumbnailUrl: "demo-loft",
    lat: 40.1846,
    lng: 44.5098,
    rooms: 2,
    areaM2: 75,
    floor: "3 / 4",
    askingUsd: 1400,
    estimateUsd: 1150,
    interval: [1020, 1290],
    comparables: 29,
    sourceUpdated: "2026-10-18",
    active: true,
    risks: [],
    explanation:
      "Above range. Designer interiors are hard to quantify; high rent is not treated as suspicious.",
  },
  {
    id: "fr-1012",
    title: "Compact 2-room, Arabkir",
    district: "Arabkir",
    street: "Kievyan St",
    thumbnailUrl: "demo-panel",
    lat: 40.2008,
    lng: 44.4932,
    rooms: 2,
    areaM2: 54,
    floor: "1 / 5",
    askingUsd: 600,
    estimateUsd: 640,
    interval: [580, 710],
    comparables: 48,
    sourceUpdated: "2026-10-17",
    active: true,
    risks: [],
    explanation: "Within range; ground-floor position slightly lowers the estimate.",
  },
];

export function getListing(id: string) {
  return LISTINGS.find((l) => l.id === id);
}

// Weekly median asking price (USD) per district. `null` = no observations that week (a gap, not zero).
export const TREND_DISTRICTS = ["Kentron", "Arabkir", "Davtashen", "Nor Nork"] as const;
export type TrendRow = { week: string } & Record<(typeof TREND_DISTRICTS)[number], number | null>;

export const WEEKLY_TRENDS: TrendRow[] = [
  { week: "2026-07-27", Kentron: 1010, Arabkir: 690, Davtashen: 420, "Nor Nork": 510 },
  { week: "2026-08-03", Kentron: 1025, Arabkir: 700, Davtashen: null, "Nor Nork": 505 },
  { week: "2026-08-10", Kentron: 1040, Arabkir: 695, Davtashen: 430, "Nor Nork": 515 },
  { week: "2026-08-17", Kentron: 1060, Arabkir: 710, Davtashen: 435, "Nor Nork": null },
  { week: "2026-08-24", Kentron: 1055, Arabkir: 720, Davtashen: 440, "Nor Nork": null },
  { week: "2026-08-31", Kentron: 1080, Arabkir: 725, Davtashen: null, "Nor Nork": 530 },
  { week: "2026-09-07", Kentron: 1095, Arabkir: 730, Davtashen: 445, "Nor Nork": 535 },
  { week: "2026-09-14", Kentron: null, Arabkir: 740, Davtashen: 450, "Nor Nork": 540 },
  { week: "2026-09-21", Kentron: 1110, Arabkir: 745, Davtashen: 455, "Nor Nork": 545 },
  { week: "2026-09-28", Kentron: 1120, Arabkir: 750, Davtashen: 450, "Nor Nork": 550 },
  { week: "2026-10-05", Kentron: 1130, Arabkir: null, Davtashen: 460, "Nor Nork": 555 },
  { week: "2026-10-12", Kentron: 1140, Arabkir: 765, Davtashen: 465, "Nor Nork": 560 },
];

export interface AreaAssessment {
  sampleSize: number;
  radiusKm: number;
  medianRentUsd: number | null;
  medianPerM2Usd: number | null;
  property: { estimateUsd: number; interval: [number, number] } | null;
}

function distKm(aLat: number, aLng: number, bLat: number, bLng: number) {
  const dLat = (aLat - bLat) * 111;
  const dLng = (aLng - bLng) * 85;
  return Math.sqrt(dLat * dLat + dLng * dLng);
}

const median = (xs: number[]): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

/** Area reference from nearby synthetic listings. A property-specific figure is only
 *  produced when floor area is supplied AND the sample is large enough. */
export function assessLocation(
  lat: number,
  lng: number,
  areaM2?: number,
  rooms?: number,
): AreaAssessment {
  const radiusKm = 2.5;
  let near = LISTINGS.filter((l) => distKm(lat, lng, l.lat, l.lng) <= radiusKm);
  if (rooms) {
    const byRooms = near.filter((l) => l.rooms === rooms);
    if (byRooms.length >= 2) near = byRooms;
  }
  const perM2 = median(near.map((l) => l.askingUsd / l.areaM2));
  const property =
    areaM2 && perM2 && near.length >= 3
      ? (() => {
          const est = Math.round(perM2 * areaM2);
          return {
            estimateUsd: est,
            interval: [Math.round(est * 0.85), Math.round(est * 1.15)] as [number, number],
          };
        })()
      : null;
  return {
    sampleSize: near.length,
    radiusKm,
    medianRentUsd: median(near.map((l) => l.askingUsd)),
    medianPerM2Usd: perM2 === null ? null : Math.round(perM2 * 10) / 10,
    property,
  };
}
