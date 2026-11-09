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
});
