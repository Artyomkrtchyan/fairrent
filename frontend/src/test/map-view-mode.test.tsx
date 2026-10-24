import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MapCanvas } from "@/components/MapCanvas";

const state = vi.hoisted(() => ({
  load: undefined as (() => void) | undefined,
  flatExists: false,
  hasBuildings: true,
  layout: vi.fn(),
  camera: vi.fn(),
  addLayer: vi.fn(),
}));

vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  NavigationControl: class {},
  AttributionControl: class {},
  Marker: class {},
  Map: class {
    addControl() {}
    on() {}
    remove() {}
    resize() {}
    jumpTo() {}
    fitBounds() {}

    once(event: string, callback: () => void) {
      if (event === "load") state.load = callback;
    }

    getZoom() {
      return 13;
    }

    getBounds() {
      return {
        getWest: () => 44.5,
        getSouth: () => 40.1,
        getEast: () => 44.6,
        getNorth: () => 40.2,
      };
    }

    getStyle() {
      return {
        layers: state.hasBuildings
          ? [
              {
                id: "provider-buildings",
                type: "fill-extrusion",
                source: "openmaptiles",
                "source-layer": "building",
                minzoom: 14,
              },
            ]
          : [],
      };
    }

    getLayer(id: string) {
      return id === "fairrent-flat-buildings" && state.flatExists ? { id } : undefined;
    }

    addLayer(layer: unknown, before?: string) {
      state.flatExists = true;
      state.addLayer(layer, before);
    }

    setLayoutProperty(...args: unknown[]) {
      state.layout(...args);
    }

    easeTo(options: unknown) {
      state.camera(options);
    }
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  state.load = undefined;
  state.flatExists = false;
  state.hasBuildings = true;

  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );

  vi.stubGlobal("matchMedia", () => ({ matches: true }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("map view modes", () => {
  it("shows flat buildings and looks straight down in 2D", () => {
    render(<MapCanvas viewMode="2d" />);
    act(() => state.load?.());

    expect(state.layout).toHaveBeenCalledWith("fairrent-flat-buildings", "visibility", "visible");
    expect(state.layout).toHaveBeenCalledWith("provider-buildings", "visibility", "none");
    expect(state.camera).toHaveBeenLastCalledWith({
      pitch: 0,
      duration: 0,
    });
  });

  it("raises buildings in 3D and restores flat buildings in 2D", () => {
    const view = render(<MapCanvas viewMode="3d" />);
    act(() => state.load?.());

    expect(state.layout).toHaveBeenCalledWith("provider-buildings", "visibility", "visible");
    expect(state.layout).toHaveBeenCalledWith("fairrent-flat-buildings", "visibility", "none");
    expect(state.camera).toHaveBeenLastCalledWith({
      pitch: 55,
      zoom: 15,
      duration: 0,
    });

    view.rerender(<MapCanvas viewMode="2d" />);

    expect(state.layout).toHaveBeenLastCalledWith("provider-buildings", "visibility", "none");
    expect(state.camera).toHaveBeenLastCalledWith({
      pitch: 0,
      duration: 0,
    });
    expect(state.addLayer).toHaveBeenCalledTimes(1);
  });

  it("does not invent buildings when the provider has no building layer", () => {
    state.hasBuildings = false;
    render(<MapCanvas viewMode="3d" />);
    act(() => state.load?.());

    expect(state.addLayer).not.toHaveBeenCalled();
    expect(state.camera).not.toHaveBeenCalled();
  });
});
