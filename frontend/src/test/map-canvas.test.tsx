import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MapCanvas } from "@/components/MapCanvas";

const state = vi.hoisted(() => ({
  maps: [] as {
    options: Record<string, unknown>;
    handlers: Record<string, () => void>;
    remove: ReturnType<typeof vi.fn>;
    jumpTo: ReturnType<typeof vi.fn>;
  }[],
  markers: [] as {
    element: HTMLButtonElement;
    remove: ReturnType<typeof vi.fn>;
    coordinates?: number[];
  }[],
  fail: false,
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
  it("uses safe keyboard-accessible price markers and removes old markers when results change", () => {
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
    expect(marker.element.textContent).toBe(point.label);
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
    expect(state.maps[0]?.options["scrollZoom"]).toBe(false);
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
