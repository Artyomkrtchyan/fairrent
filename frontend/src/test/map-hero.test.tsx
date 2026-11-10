import { cleanup, fireEvent, render as renderReact, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import fixtures from "../../../contracts/fixtures.json";
import type { MapListing } from "@/lib/map-listings";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";
import { MapHero } from "@/components/MapHero";

function render(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return renderReact(ui, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

vi.mock("@/lib/prefs", () => ({ usePrefs: () => ({ format: (value: number) => `${value}` }) }));
vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: ReactNode }) => <a href="/listings/example">{children}</a>,
}));

vi.mock("@/components/MapCanvas", () => ({
  MapCanvas: ({
    expanded = false,
    onBoundsChange,
    onCameraChange,
    camera,
    points = [],
    onOverlap,
    rentColorMode,
  }: {
    points?: { id: string }[];
    rentColorMode?: "buildings" | "ground";
    onOverlap?: (ids: string[]) => void;
    camera?: { zoom: number };
    onCameraChange?: (camera: {
      center: [number, number];
      zoom: number;
      pitch: number;
      bearing: number;
    }) => void;
    expanded?: boolean;
    onBoundsChange?: ((bounds: [number, number, number, number]) => void) | undefined;
  }) => (
    <div
      data-testid={expanded ? "expanded-map" : "embedded-map"}
      data-initial-zoom={camera?.zoom}
      data-marker-count={points.length}
      data-rent-color-mode={rentColorMode}
    >
      Map preview
      <button onClick={() => onOverlap?.(points.map((point) => point.id))}>
        Select overlapping rentals
      </button>
      <button
        onClick={() => {
          onCameraChange?.({ center: [44.55, 40.15], zoom: 15, pitch: 0, bearing: 0 });
          onBoundsChange?.([44.5, 40.1, 44.6, 40.2]);
        }}
      >
        Move map in test
      </button>
      <button onClick={() => onBoundsChange?.([44, 40, 45, 41])}>Zoom out in test</button>
    </div>
  ),
}));

beforeAll(() => {
  for (const method of ["showModal", "close"]) {
    if (!(method in HTMLDialogElement.prototype)) {
      Object.defineProperty(HTMLDialogElement.prototype, method, {
        configurable: true,
        writable: true,
        value() {},
      });
    }
  }
});

beforeEach(() => {
  // jsdom does not implement the native modal API; real-browser checks cover it.
  vi.spyOn(HTMLDialogElement.prototype, "showModal").mockImplementation(function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  });
  vi.spyOn(HTMLDialogElement.prototype, "close").mockImplementation(function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("framed map introduction", () => {
  it("defaults to building-only colors and switches instantly to the saved ground surface", async () => {
    render(<MapHero />);
    const map = await screen.findByTestId("embedded-map");
    expect(map).toHaveAttribute("data-rent-color-mode", "buildings");
    fireEvent.change(screen.getByRole("combobox", { name: "Rent colors on" }), {
      target: { value: "ground" },
    });
    expect(map).toHaveAttribute("data-rent-color-mode", "ground");
    fireEvent.change(screen.getByRole("combobox", { name: "Rent colors on" }), {
      target: { value: "buildings" },
    });
    expect(map).toHaveAttribute("data-rent-color-mode", "buildings");
  });

  it("shows the complete location response before applying a map area", async () => {
    const mapLocations = Array.from({ length: 101 }, (_, index) => ({
      id: String(index),
      latitude: 40.18,
      longitude: 44.51,
      coordinate_confidence: "exact" as const,
    }));
    render(<MapHero mapLocations={mapLocations} />);
    expect(await screen.findByTestId("embedded-map")).toHaveAttribute("data-marker-count", "0");
    expect(screen.getByRole("checkbox", { name: /Metro/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Universities/ })).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("Apartment dots"));
    expect(screen.getByTestId("embedded-map")).toHaveAttribute("data-marker-count", "101");
    expect(screen.getByText(/101 rentals with usable locations/)).toBeInTheDocument();
  });

  it("shows the first rental details immediately when multiple points overlap", async () => {
    const first = fixtures.listings.value.items[0] as MapListing;
    const second = { ...first, id: "second-rental", title: "Second apartment" };
    render(<MapHero listings={[first, second]} bbox="44.5,40.1,44.6,40.2" />);
    fireEvent.click(screen.getByLabelText("Apartment dots"));
    fireEvent.click(await screen.findByRole("button", { name: "Select overlapping rentals" }));
    const preview = screen.getByRole("region", { name: "Selected rental" });
    expect(within(preview).getByText("Rental 1 of 2 at this location")).toBeInTheDocument();
    expect(within(preview).getByText(first.title!)).toBeInTheDocument();
    expect(within(preview).getByText(/rooms/)).toBeInTheDocument();
    expect(within(preview).getByText("View details →")).toBeInTheDocument();
    expect(screen.queryByText("View rental 1")).not.toBeInTheDocument();

    fireEvent.click(within(preview).getByRole("button", { name: "Next rental at this location" }));
    expect(within(preview).getByText("Rental 2 of 2 at this location")).toBeInTheDocument();
    expect(within(preview).getByText("Second apartment")).toBeInTheDocument();

    fireEvent.click(within(preview).getByRole("button", { name: "Previous rental at this location" }));
    expect(within(preview).getByText("Rental 1 of 2 at this location")).toBeInTheDocument();
  });

  it("offers Clear area in both toolbars only when an area is applied", async () => {
    const onClearArea = vi.fn();
    const view = render(<MapHero onSearchArea={vi.fn()} onClearArea={onClearArea} />);
    expect(screen.queryByRole("button", { name: "Clear area" })).not.toBeInTheDocument();
    view.rerender(
      <MapHero bbox="44.5,40.1,44.6,40.2" onSearchArea={vi.fn()} onClearArea={onClearArea} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Clear area" }));
    expect(onClearArea).toHaveBeenCalledOnce();
    await screen.findByTestId("embedded-map");
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Clear area" }));
    expect(onClearArea).toHaveBeenCalledTimes(2);
  });

  it("keeps optional layers off and opens the rent guide only on request", async () => {
    const listings = fixtures.listings.value.items as MapListing[];
    const searchArea = vi.fn();
    const view = render(<MapHero listings={listings} onSearchArea={searchArea} />);
    const map = await screen.findByTestId("embedded-map");
    expect(map).toHaveAttribute("data-marker-count", "0");
    expect(screen.getByRole("checkbox", { name: /Metro/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Universities/ })).not.toBeChecked();
    expect(screen.queryByLabelText("Area rent colour legend")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open district rent price guide" }));
    expect(screen.getByLabelText("Area rent colour legend")).toHaveTextContent("Demo data");
    expect(screen.getByLabelText("Area rent colour legend")).toHaveTextContent("USD / m² / month");
    fireEvent.click(screen.getByRole("button", { name: "Close district rent price guide" }));
    expect(screen.queryByLabelText("Area rent colour legend")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move map in test" }));
    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    expect(searchArea).toHaveBeenCalledWith("44.5,40.1,44.6,40.2");
    view.rerender(
      <MapHero bbox="44.5,40.1,44.6,40.2" listings={listings} onSearchArea={searchArea} />,
    );
    expect(map).toHaveAttribute("data-marker-count", "1");
    fireEvent.click(screen.getByLabelText("Apartment dots"));
    expect(map).toHaveAttribute("data-marker-count", "0");
    fireEvent.click(screen.getByLabelText("Apartment dots"));
    expect(map).toHaveAttribute("data-marker-count", "1");
  });

  it("does not feed fullscreen movement back into the controlled camera", async () => {
    render(<MapHero onSearchArea={vi.fn()} />);
    await screen.findByTestId("embedded-map");
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    const dialog = screen.getByRole("dialog");
    const map = within(dialog).getByTestId("expanded-map");
    expect(screen.queryByTestId("embedded-map")).not.toBeInTheDocument();
    expect(map).toHaveAttribute("data-initial-zoom", "13");
    fireEvent.click(within(dialog).getByRole("button", { name: "Move map in test" }));
    expect(map).toHaveAttribute("data-initial-zoom", "13");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close map" }));
    expect(screen.getByTestId("embedded-map")).toHaveAttribute("data-initial-zoom", "15");
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    expect(within(screen.getByRole("dialog")).getByTestId("expanded-map")).toHaveAttribute(
      "data-initial-zoom",
      "15",
    );
  });

  it("waits for an explicit area search and rejects oversized viewports", async () => {
    const onSearchArea = vi.fn();
    const view = render(<MapHero onSearchArea={onSearchArea} />);
    expect(screen.getByRole("button", { name: "Search this area" })).toBeDisabled();
    fireEvent.click(await screen.findByRole("button", { name: "Move map in test" }));
    expect(onSearchArea).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Search this area" }));
    expect(onSearchArea).toHaveBeenCalledWith("44.5,40.1,44.6,40.2");
    view.rerender(<MapHero bbox="44.5,40.1,44.6,40.2" onSearchArea={onSearchArea} />);
    expect(screen.getByRole("button", { name: "Search this area" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Zoom out in test" }));
    expect(screen.getByRole("button", { name: "Search this area" })).toBeDisabled();
    expect(screen.getByText(/Zoom in to search a smaller area/)).toBeInTheDocument();
  });

  it("opens only with the Expand action and returns focus after Close", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo");
    render(<MapHero />);
    fireEvent.click(await screen.findByTestId("embedded-map"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Expand map" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Explore Yerevan" });
    expect(within(dialog).getByTestId("expanded-map")).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close map" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(trigger).toHaveFocus();
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: "instant" }));
  });

  it("handles the native Escape/cancel event", () => {
    render(<MapHero />);
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    fireEvent(
      screen.getByRole("dialog"),
      new Event("cancel", { bubbles: false, cancelable: true }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand map" })).toHaveFocus();
  });

  it("moves to the existing filters without changing the search URL", () => {
    const scrollIntoView = vi.fn();
    const target = document.createElement("div");
    target.id = "rental-catalogue";
    target.tabIndex = -1;
    target.scrollIntoView = scrollIntoView;
    document.body.append(target);
    const previousUrl = window.location.href;
    render(<MapHero />);
    fireEvent.click(screen.getByRole("link", { name: "Browse rentals" }));
    expect(target).toHaveFocus();
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(window.location.href).toBe(previousUrl);
    target.remove();
  });
});
