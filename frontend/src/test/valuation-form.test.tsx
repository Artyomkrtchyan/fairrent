import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import fixtures from "../../../contracts/fixtures.json";
import { requestValuation } from "@/api/valuations";
import { Valuation } from "@/routes/valuation";

vi.mock("@/api/valuations", () => ({ requestValuation: vi.fn() }));
vi.mock("@/api/client", () => ({ apiMode: "real" }));
vi.mock("@/components/MapCanvas", () => ({
  MapCanvas: ({ onPickCoordinate }: { onPickCoordinate?: (lat: number, lng: number) => void }) => (
    <button type="button" onClick={() => onPickCoordinate?.(40.181234, 44.512345)}>
      Choose coordinate on map
    </button>
  ),
}));
vi.mock("@/components/ui-bits", () => ({
  Money: ({ usd }: { usd: number }) => <span>{usd} USD</span>,
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
  RateNote: () => null,
}));

const request = vi.mocked(requestValuation);
type Result = Awaited<ReturnType<typeof requestValuation>>;

function renderForm() {
  const client = new QueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  render(<Valuation />, { wrapper: Wrapper });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Assess location" }));
}

afterEach(() => {
  cleanup();
  request.mockReset();
});

describe("location assessment form", () => {
  it("sends property inputs and presents the API result", async () => {
    request.mockResolvedValue(fixtures.valuation.value as Result);
    renderForm();
    fireEvent.change(screen.getByLabelText("Rooms"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/floor area/i), { target: { value: "50" } });
    submit();

    expect(await screen.findByText("Estimated rent")).toBeInTheDocument();
    expect(request.mock.calls.map(([body]) => body)).toEqual([
      {
        latitude: 40.1872,
        longitude: 44.5152,
        area_sqm: 50,
        rooms: 2,
        radius_m: 1000,
        window_days: 30,
      },
    ]);
    expect(screen.getByText(/Monthly rent standard deviation/)).toBeInTheDocument();
  });

  it("uses the area reference returned for coordinates alone", async () => {
    request.mockResolvedValue(fixtures["area-reference"].value as Result);
    renderForm();
    submit();

    expect(await screen.findByText("Area reference rent")).toBeInTheDocument();
    expect(request.mock.calls.map(([body]) => body)).toEqual([
      {
        latitude: 40.1872,
        longitude: 44.5152,
        radius_m: 1000,
        window_days: 30,
      },
    ]);
  });

  it("shows the reason when the API withholds a valuation", async () => {
    request.mockResolvedValue(fixtures["valuation-sparse"].value as Result);
    renderForm();
    submit();

    expect(
      await screen.findByText(fixtures["valuation-sparse"].value.explanation),
    ).toBeInTheDocument();
    expect(screen.getByText("Area reference rent").nextElementSibling).toHaveTextContent(
      "Not available",
    );
  });

  it("uses a clicked map coordinate for the next request", async () => {
    request.mockResolvedValue(fixtures["area-reference"].value as Result);
    renderForm();
    fireEvent.click(await screen.findByRole("button", { name: "Choose coordinate on map" }));
    submit();

    await waitFor(() => expect(request.mock.calls[0]?.[0]).toEqual(expect.objectContaining({
      latitude: 40.181234,
      longitude: 44.512345,
    })));
  });

  it("requires positive area for a rooms-based property assessment", () => {
    renderForm();
    fireEvent.change(screen.getByLabelText("Rooms"), { target: { value: "2" } });
    submit();

    expect(screen.getByRole("alert")).toHaveTextContent("Enter floor area");
    expect(request).not.toHaveBeenCalled();
  });

  it("displays API errors without a synthetic result", async () => {
    request.mockRejectedValue(new Error("Coordinates are outside coverage."));
    renderForm();
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Coordinates are outside coverage.");
    expect(screen.queryByRole("heading", { name: "Market assessment" })).not.toBeInTheDocument();
  });
});
