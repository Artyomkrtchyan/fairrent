import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import { getListings } from "@/api/listings";
import { MarketAnalytics } from "@/routes/analytics";

vi.mock("@/api/listings", () => ({ getListings: vi.fn() }));

vi.mock("@/lib/prefs", () => ({
  usePrefs: () => ({
    currency: "USD",
    format: (value: number) => `${value.toFixed(2)} USD`,
  }),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: () => null,
  Bar: () => null,
  BarChart: () => null,
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  render(
    <QueryClientProvider client={client}>
      <MarketAnalytics />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getListings).mockResolvedValue(
    fixtures.listings.value as Awaited<ReturnType<typeof getListings>>,
  );
});

afterEach(cleanup);

describe("market analytics page", () => {
  it("shows the current listings snapshot without a weekly history selector", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Market analytics" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current listing snapshot" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Published weekly history" })).not.toBeInTheDocument();
    expect(screen.queryByText("Weekly median asking rent")).not.toBeInTheDocument();
    expect(await screen.findByText("600.00 USD")).toBeInTheDocument();
  });

  it("keeps the current listing snapshot table functional", async () => {
    renderPage();
    await screen.findByText("600.00 USD");
    fireEvent.click(screen.getByRole("button", { name: /^table$/i }));
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Kentron")).toBeInTheDocument();
  });
  it("loads every page within the API's 100-listing limit", async () => {
    const original = fixtures.listings.value.items[0]!;
    vi.mocked(getListings).mockImplementation(async (_signal, options) => {
      const page = options?.page ?? 1;
      const count = page === 4 ? 1 : 100;
      return {
        ...fixtures.listings.value,
        page,
        page_size: 100,
        total: 301,
        has_more: page < 4,
        items: Array.from({ length: count }, (_, index) => ({
          ...original,
          id: `00000000-0000-4000-8000-${String((page - 1) * 100 + index).padStart(12, "0")}`,
          external_id: `analytics-${page}-${index}`,
          property_id: `analytics-property-${page}-${index}`,
          dedup_group_id: null,
        })),
      } as Awaited<ReturnType<typeof getListings>>;
    });
    renderPage();
    expect(await screen.findByText(/Loaded 301 of 301 active listing rows/)).toBeInTheDocument();
    expect(vi.mocked(getListings).mock.calls.map(([, options]) => options?.page).sort((a, b) => Number(a) - Number(b))).toEqual([1, 2, 3, 4]);
    expect(vi.mocked(getListings).mock.calls.every(([, options]) => options?.page_size === 100)).toBe(true);
  });

});
