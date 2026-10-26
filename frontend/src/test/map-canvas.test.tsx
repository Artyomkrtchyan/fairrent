import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MapCanvas } from "@/components/MapCanvas";

const state = vi.hoisted(() => ({
  maps: [] as {
    options: Record<string, unknown>;
    handlers: Record<string, () => void>;
    remove: ReturnType<typeof vi.fn>;
    jumpTo: ReturnType<typeof vi.fn>;
    addSource: ReturnType<typeof vi.fn>;
    addLayer: ReturnType<typeof vi.fn>;
    removeSource: ReturnType<typeof vi.fn>;
    removeLayer: ReturnType<typeof vi.fn>;
  }[],
  markers: [] as {
    element: HTMLButtonElement;
    remove: ReturnType<typeof vi.fn>;
    coordinates?: number[];
  }[],
  mode: "mock",
  fail: false,
}));

vi.mock("@/api/client", () => ({
  get apiMode() {
    return state.mode;
  },
}));
vi.mock("@/lib/map-demo-surface", () => ({
  DEMO_SURFACE: { bounds: [44.44, 40.11, 44.6, 40.24] },
  demoSurfaceImage: () => "data:image/png;base64,test-only",
}));

vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  NavigationControl: class {},
  AttributionControl: class {},
  Marker: class {
    element: HTMLButtonElement;
    coordinates?: number[];
    remove = vi.fn();
    constructor({ element }: { element: HTMLButtonElement }) {
      this.element = element;
      state.markers.push(this);
    }
    setLngLat(coordinates: number[]) {
      this.coordinates = coordinates;
      return this;
    }
    addTo() {
      return this;
    }
  },
  Map: class {
    options: Record<string, unknown>;
    handlers: Record<string, () => void> = {};
    remove = vi.fn();
    jumpTo = vi.fn();
    resize = vi.fn();
    addSource = vi.fn();
    addLayer = vi.fn();
    removeSource = vi.fn();
    removeLayer = vi.fn();
    getStyle() {
      return { layers: [{ id: "roads", type: "line" }] };
    }
    getLayer() {
      return true;
    }
    getSource() {
      return true;
    }
    constructor(options: Record<string, unknown>) {
      if (state.fail) throw new Error("WebGL unavailable");
      this.options = options;
      state.maps.push(this);
    }
    addControl() {
      return this;
    }
    on(name: string, callback: () => void) {
      this.handlers[name] = callback;
      return this;
    }
    once(name: string, callback: () => void) {
      this.handlers[name] = callback;
      return this;
    }
    fitBounds = vi.fn();
    getBounds() {
      return {
        getWest: () => 44.5,
        getSouth: () => 40.1,
        getEast: () => 44.6,
        getNorth: () => 40.2,
      };
    }
    getCenter() {
      return { lng: 44.52, lat: 40.18 };
    }
    getZoom() {
      return 14;
    }
    getPitch() {
      return 0;
    }
    getBearing() {
      return 0;
    }
  },
}));

beforeEach(() => {
  state.maps = [];
  state.markers = [];
  state.fail = false;
  state.mode = "mock";
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("map canvas", () => {
  it("uses separately labelled keyboard buttons for nearby places and removes them when disabled", () => {
    const onSelectPlace = vi.fn();
    const places = [
      {
        id: "metro",
        name: "<b>Test metro</b>",
        type: "metro" as const,
        latitude: 40.18,
        longitude: 44.51,
      },
    ];
    const view = render(
      <MapCanvas places={places} selectedPlaceId="metro" onSelectPlace={onSelectPlace} />,
    );
    const marker = state.markers[0]!;
    expect(marker.element.textContent).toBe("M");
    expect(marker.element.querySelector("b")).toBeNull();
    expect(marker.element.getAttribute("aria-label")).toContain("Metro station: <b>Test metro</b>");
    expect(marker.element.getAttribute("aria-pressed")).toBe("true");
    marker.element.click();
    expect(onSelectPlace).toHaveBeenCalledWith("metro");
    view.rerender(<MapCanvas places={[]} onSelectPlace={onSelectPlace} />);
    expect(marker.remove).toHaveBeenCalledOnce();
  });

  it("adds the synthetic raster below roads after style load and cleans up on disable", () => {
    const view = render(<MapCanvas showDemoSurface />);
    const map = state.maps[0]!;
    expect(map.addSource).not.toHaveBeenCalled();
    act(() => map.handlers["load"]?.());
    expect(map.addSource).toHaveBeenCalledWith(
      "fairrent-synthetic-rent-surface",
      expect.objectContaining({ type: "image" }),
    );
    expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({ type: "raster" }), "roads");
    view.rerender(<MapCanvas showDemoSurface={false} />);
    expect(map.removeLayer).toHaveBeenCalledOnce();
    expect(map.removeSource).toHaveBeenCalledOnce();
  });
  it("never adds synthetic market colours in real API mode", () => {
    state.mode = "real";
    render(<MapCanvas showDemoSurface />);
    act(() => state.maps[0]?.handlers["load"]?.());
    expect(state.maps[0]?.addSource).not.toHaveBeenCalled();
  });

  it("uses safe keyboard-accessible dot markers and removes old markers when results change", () => {
    const onSelect = vi.fn();
    const point = {
      id: "rental-one",
      longitude: 44.51,
      latitude: 40.18,
      label: "<img onerror=alert(1)>",
      approximate: true,
    };
    const view = render(<MapCanvas points={[point]} onSelect={onSelect} selectedId={point.id} />);
    const marker = state.markers[0]!;
    expect(marker.coordinates).toEqual([44.51, 40.18]);
    expect(marker.element.tagName).toBe("BUTTON");
    expect(marker.element.querySelector("img")).toBeNull();
    expect(marker.element.textContent).toBe("");
    expect(marker.element.title).toBe(point.label);
    expect(marker.element.getAttribute("aria-label")).toContain(point.label);
    expect(marker.element.getAttribute("aria-label")).toContain("approximate location");
    expect(marker.element.getAttribute("aria-pressed")).toBe("true");
    marker.element.click();
    expect(onSelect).toHaveBeenCalledWith(point.id);
    view.rerender(<MapCanvas points={[]} onSelect={onSelect} />);
    expect(marker.remove).toHaveBeenCalledOnce();
    expect(state.maps).toHaveLength(1);
  });

  it("preserves page scrolling in the embedded map and enables zoom in the expanded view", () => {
    const embedded = render(<MapCanvas />);
    expect(state.maps[0]?.options["scrollZoom"]).toBe(true);
    expect(state.maps[0]?.options["cooperativeGestures"]).toBe(true);
    embedded.unmount();
    render(<MapCanvas expanded />);
    expect(state.maps[1]?.options["scrollZoom"]).toBe(true);
    expect(state.maps[1]?.options["cooperativeGestures"]).toBe(false);
  });

  it("stops loading on map load and releases the renderer on unmount", () => {
    const view = render(<MapCanvas />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading Yerevan");
    act(() => state.maps[0]?.handlers["load"]?.());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    view.unmount();
    expect(state.maps[0]?.remove).toHaveBeenCalledOnce();
  });

  it("updates the camera without recreating the map", () => {
    const onCameraChange = vi.fn();
    const view = render(<MapCanvas onCameraChange={onCameraChange} />);
    act(() => state.maps[0]?.handlers["moveend"]?.());
    expect(onCameraChange).toHaveBeenCalledWith({
      center: [44.52, 40.18],
      zoom: 14,
      pitch: 0,
      bearing: 0,
    });
    const camera = { center: [44.53, 40.19] as [number, number], zoom: 15, pitch: 0, bearing: 0 };
    view.rerender(<MapCanvas camera={camera} onCameraChange={onCameraChange} />);
    expect(state.maps).toHaveLength(1);
    expect(state.maps[0]?.jumpTo).toHaveBeenLastCalledWith(camera);
  });

  it("shows a fallback when the renderer cannot start", () => {
    state.fail = true;
    render(<MapCanvas />);
    expect(screen.getByRole("status")).toHaveTextContent("could not start");
  });

  it("shows a timeout without blocking rental browsing", () => {
    vi.useFakeTimers();
    render(<MapCanvas />);
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.getByRole("status")).toHaveTextContent("still browse the rentals");
  });
});
