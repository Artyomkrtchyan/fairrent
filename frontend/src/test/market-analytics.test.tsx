import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import { getMarketIndex, type MarketIndexPage } from "@/api/market";
import { MarketAnalytics } from "@/routes/analytics";

vi.mock("@/api/market", () => ({
  getMarketIndex: vi.fn(),
}));

vi.mock("@/lib/prefs", () => ({
  usePrefs: () => ({
    currency: "USD",
    format: (value: number) => `${value.toFixed(2)} USD`,
  }),
}));

// Test accessible values and controls without requiring browser chart dimensions.
vi.mock("recharts", () => ({
  ResponsiveContainer: () => null,
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

const response = fixtures["market-index"].value as MarketIndexPage;
const empty = fixtures["market-empty"].value as MarketIndexPage;

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  render(
    <QueryClientProvider client={client}>
      <MarketAnalytics />
    </QueryClientProvider>,
  );

  fireEvent.click(screen.getByRole("button", { name: /^table$/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getMarketIndex).mockResolvedValue(response);
});

afterEach(cleanup);

describe("market analytics page", () => {
  it("displays the API median and changes measure without changing the source data", async () => {
    renderPage();
    const table = await screen.findByRole("table");

    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();
    expect(within(table).getByText("3")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Measure"), {
      target: { value: "m2" },
    });

    expect(within(table).getByText("12.00 USD")).toBeInTheDocument();
    expect(within(table).getByRole("caption")).toHaveTextContent("USD/month/m²");
  });

  it("keeps missing per-area values separate from monthly values and counts", async () => {
    const record = {
      ...response.items[0]!,
      sample_count: 8,
      area_sample_count: 2,
      median_usd_m2: null,
    };

    vi.mocked(getMarketIndex).mockResolvedValue({
      ...response,
      items: [record],
    });

    renderPage();
    const table = await screen.findByRole("table");

    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();
    expect(within(table).getByText("8")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Measure"), {
      target: { value: "m2" },
    });

    expect(within(table).getByText("Unavailable")).toBeInTheDocument();
    expect(within(table).getByText("2")).toBeInTheDocument();
    expect(within(table).queryByText("0.00 USD")).not.toBeInTheDocument();
  });

  it("applies a neighborhood selection and shows an empty response honestly", async () => {
    renderPage();
    await screen.findByRole("table");
    vi.mocked(getMarketIndex).mockResolvedValue(empty);

    fireEvent.change(screen.getByLabelText("Neighborhood"), {
      target: { value: "arabkir" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      await screen.findByText("No published weekly data for this selection."),
    ).toBeInTheDocument();

    expect(getMarketIndex).toHaveBeenLastCalledWith(
      expect.objectContaining({ district_id: "arabkir", page: 1 }),
      expect.anything(),
    );
  });

  it("rejects reversed dates before requesting another response", async () => {
    renderPage();
    await screen.findByRole("table");
    const calls = vi.mocked(getMarketIndex).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Week starting from"), {
      target: { value: "2026-10-26" },
    });
    fireEvent.change(screen.getByLabelText("Week starting through"), {
      target: { value: "2026-10-12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The start date must not be after the end date.",
    );
    expect(getMarketIndex).toHaveBeenCalledTimes(calls);
  });

  it("shows API failures and recovers through Retry without demo fallback", async () => {
    vi.mocked(getMarketIndex).mockRejectedValue(new Error("API offline"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load market analytics.");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    vi.mocked(getMarketIndex).mockResolvedValue(response);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    const table = await screen.findByRole("table");
    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();
  });

  it("preserves loaded weeks when the next page fails and retries that page", async () => {
    const firstPage: MarketIndexPage = {
      ...response,
      page_size: 1,
      total: 2,
      has_more: true,
      available_to: "2026-10-19",
    };

    const secondPage: MarketIndexPage = {
      ...firstPage,
      page: 2,
      has_more: false,
      items: [
        {
          ...response.items[0]!,
          period_start: "2026-10-19",
          period_end: "2026-10-25",
          median_usd_month: 700,
          median_usd_m2: 14,
          data_as_of: "2026-10-24T08:00:00Z",
          freshness: {
            ...response.items[0]!.freshness,
            data_as_of: "2026-10-24T08:00:00Z",
          },
        },
      ],
    };

    vi.mocked(getMarketIndex)
      .mockResolvedValueOnce(firstPage)
      .mockRejectedValueOnce(new Error("Next page unavailable"))
      .mockResolvedValueOnce(secondPage);

    renderPage();
    const table = await screen.findByRole("table");

    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Load more weeks",
      }),
    );

    await screen.findByRole("alert");
    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 weekly records loaded.")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Retry loading more weeks",
      }),
    );

    expect(await within(table).findByText("700.00 USD")).toBeInTheDocument();
    expect(within(table).getByText("600.00 USD")).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(3);

    expect(vi.mocked(getMarketIndex).mock.calls.map(([query]) => query?.page)).toEqual([1, 2, 2]);
  });
});
