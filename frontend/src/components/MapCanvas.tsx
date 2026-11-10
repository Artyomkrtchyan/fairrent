import { useEffect, useRef, useState } from "react";
import {
  Map,
  NavigationControl,
  AttributionControl,
  Marker,
  Popup,
  setWorkerUrl,
  type GeoJSONSource,
} from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";

import type { InfrastructurePoint } from "@/api/infrastructure";
import { apiMode } from "@/api/client";
import { DEMO_SURFACE, demoRentValue, demoSurfaceImage } from "@/lib/map-demo-surface";
import { renderSmoothRentSurface } from "@/lib/map-smooth-rent-surface";
import { parseMapBounds, type MapBounds } from "@/lib/map-bounds";
import type { DistrictPrice } from "@/lib/district-price-layer";
import districtGeojson from "@/data/yerevan-districts.geojson?raw";
import { createBuildingRentSampler, footprintCenter, rentGradientColor } from "@/lib/map-building-rent-colors";

setWorkerUrl(mapWorkerUrl);

export interface RentalMapPoint {
  id: string;
  longitude: number;
  latitude: number;
  label: string;
  approximate: boolean;
}

const EMPTY_PLACES: readonly InfrastructurePoint[] = [];

const EMPTY_POINTS: readonly RentalMapPoint[] = [];

const DEFAULT_STYLE = "https://tiles.openfreemap.org/styles/liberty";

export interface MapCamera {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

const DEFAULT_CAMERA: MapCamera = {
  center: [44.51562, 40.17767],
  zoom: 13,
  pitch: 0,
  bearing: 0,
};

interface Props {
  viewMode?: "2d" | "3d";
  rentColorMode?: "buildings" | "ground";
  places?: readonly InfrastructurePoint[];
  districtPrices?: readonly DistrictPrice[] | undefined;
  priceRange?: { minimum: number; maximum: number } | null;
  selectedPlaceId?: string | undefined;
  onSelectPlace?: (id: string) => void;
  onPickCoordinate?: (latitude: number, longitude: number) => void;
  pickedCoordinate?: { latitude: number; longitude: number } | null;
  showDemoSurface?: boolean;
  bbox?: string | undefined;
  onBoundsChange?: ((bounds: MapBounds) => void) | undefined;
  points?: readonly RentalMapPoint[];
  selectedId?: string | undefined;
  onSelect?: (id: string) => void;
  clustered?: boolean;
  onOverlap?: (ids: string[]) => void;
  expanded?: boolean;
  camera?: MapCamera;
  onCameraChange?: (camera: MapCamera) => void;
}

export function MapCanvas({
  viewMode = "2d",
  rentColorMode = "buildings",
  places = EMPTY_PLACES,
  districtPrices,
  priceRange,
  selectedPlaceId,
  onSelectPlace,
  onPickCoordinate,
  pickedCoordinate,
  showDemoSurface = false,
  bbox,
  onBoundsChange,
  expanded = false,
  camera,
  onCameraChange,
  points = EMPTY_POINTS,
  selectedId,
  onSelect,
  clustered = false,
  onOverlap,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Map | null>(null);
  const placeButtons = useRef<HTMLButtonElement[]>([]);
  const markerButtons = useRef<HTMLButtonElement[]>([]);
  const initialOptions = useRef({ expanded, camera: camera ?? DEFAULT_CAMERA });
  const cameraCallback = useRef(onCameraChange);
  const boundsCallback = useRef(onBoundsChange);
  const pickCallback = useRef(onPickCoordinate);
  useEffect(() => {
    pickCallback.current = onPickCoordinate;
  }, [onPickCoordinate]);
  useEffect(() => {
    boundsCallback.current = onBoundsChange;
  }, [onBoundsChange]);
  const [styleReady, setStyleReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    cameraCallback.current = onCameraChange;
  }, [onCameraChange]);

  useEffect(() => {
    if (!container.current) return;

    let map: Map | undefined;
    let observer: ResizeObserver | undefined;
    let disposed = false;

    const timeout = window.setTimeout(() => {
      if (!disposed) {
        setLoading(false);
        setError("The map is taking too long to load. You can still browse the rentals below.");
      }
    }, 20_000);

    try {
      const options = initialOptions.current;
      map = new Map({
        container: container.current,
        style: import.meta.env["VITE_MAP_STYLE_URL"] || DEFAULT_STYLE,
        ...options.camera,
        attributionControl: false,
        // Cooperative gestures preserve page scrolling in the embedded map.
        scrollZoom: true,
        cooperativeGestures: !options.expanded,
      });
      instance.current = map;

      map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
      map.addControl(new AttributionControl({ compact: true }), "bottom-right");

      const activeMap = map;
      map.on("click", (event) => {
        if (!disposed) pickCallback.current?.(event.lngLat.lat, event.lngLat.lng);
      });

      map.on("moveend", () => {
        if (disposed) return;
        const bounds = activeMap.getBounds();
        boundsCallback.current?.([
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ]);
        const center = activeMap.getCenter();
        cameraCallback.current?.({
          center: [center.lng, center.lat],
          zoom: activeMap.getZoom(),
          pitch: activeMap.getPitch(),
          bearing: activeMap.getBearing(),
        });
      });

      map.once("load", () => {
        if (disposed) return;
        window.clearTimeout(timeout);
        setLoading(false);
        setError(null);
        setStyleReady(true);
        const bounds = activeMap.getBounds();
        boundsCallback.current?.([
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth(),
        ]);
      });

      map.on("error", () => {
        if (disposed) return;
        setError(
          "Some map content could not load. Check your connection; rental browsing is still available.",
        );
      });

      observer = new ResizeObserver(() => activeMap.resize());
      observer.observe(container.current);
    } catch {
      window.clearTimeout(timeout);
      setLoading(false);
      setError("The map could not start in this browser. You can still browse the rentals below.");
    }

    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      observer?.disconnect();
      instance.current = null;
      map?.remove();
    };
  }, []);

  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady || !districtPrices?.length || !priceRange) return;

    const sourceId = "fairrent-district-price-data";
    const fillId = "fairrent-district-prices";
    const prices = new globalThis.Map<string, DistrictPrice>(districtPrices.map((item) => [item.districtId, item]));
    const registry = JSON.parse(districtGeojson) as {
      type: "FeatureCollection";
      features: Array<{
        type: "Feature";
        geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
        properties: { district_id: string; name: string };
      }>;
    };
    const data = {
      type: "FeatureCollection" as const,
      features: registry.features.map((feature) => {
        const price = prices.get(feature.properties.district_id);
        return {
          type: "Feature" as const,
          geometry: feature.geometry,
          properties: {
            name: feature.properties.name,
            has_data: Boolean(price),
            price_m2: price?.medianUsdM2 ?? 0,
            sample_count: price?.areaSampleCount ?? 0,
            stale: price?.stale ?? false,
          },
        };
      }),
    };
    // Keep a transparent, interactive district layer so clicks still reveal the
    // actual district median and supporting listing count, not interpolated values.
    map.addSource(sourceId, { type: "geojson", data: data as Parameters<GeoJSONSource["setData"]>[0] });
    map.addLayer({
      id: fillId,
      source: sourceId,
      type: "fill",
      filter: ["==", ["get", "has_data"], true],
      paint: { "fill-opacity": 0 },
    });

    const entered = map.on("mouseenter", fillId, () => { map.getCanvas().style.cursor = "pointer"; });
    const left = map.on("mouseleave", fillId, () => { map.getCanvas().style.cursor = ""; });
    const clicked = map.on("click", fillId, (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const props = feature.properties;
      const name = String(props["name"] ?? "District");
      const value = Number(props["price_m2"]);
      const count = Number(props["sample_count"]);
      const stale = props["stale"] === true || props["stale"] === "true";
      const label = `${name}: ${value.toFixed(2)} USD/m²/month median asking rent · ${count} supporting listings${stale ? " · stale data" : ""}`;
      new Popup({ closeButton: true, maxWidth: "320px" })
        .setLngLat(event.lngLat)
        .setText(label)
        .addTo(map);
    });
    return () => {
      clicked.unsubscribe();
      entered.unsubscribe();
      left.unsubscribe();
      map.getCanvas().style.cursor = "";
      if (instance.current !== map) return;
      if (map.getLayer(fillId)) map.removeLayer(fillId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [styleReady, districtPrices, priceRange]);

  useEffect(() => {
    if (camera) instance.current?.jumpTo(camera);
  }, [camera]);

  // One-click comparison and rollback to the preserved, city-clipped ground
  // surface. The building-only experiment is the default, never both at once.
  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady || rentColorMode !== "ground") return;

    const name = "fairrent-preserved-ground-rent-gradient";
    let bounds: readonly [number, number, number, number];
    let url: string;
    if (showDemoSurface) {
      bounds = DEMO_SURFACE.bounds;
      url = demoSurfaceImage();
    } else {
      if (!districtPrices?.length || !priceRange) return;
      const registry = JSON.parse(districtGeojson) as {
        features: Array<{
          geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
          properties: { district_id: string; name: string };
        }>;
      };
      const surface = renderSmoothRentSurface(
        registry.features,
        new globalThis.Map(districtPrices.map((item) => [item.districtId, item])),
        priceRange,
      );
      bounds = surface.bounds;
      url = surface.url;
    }
    const [west, south, east, north] = bounds;
    map.addSource(name, {
      type: "image",
      url,
      coordinates: [[west, north], [east, north], [east, south], [west, south]],
    });
    const before = map.getStyle().layers?.find((layer) =>
      showDemoSurface ? (layer.type === "line" || layer.type === "symbol") : layer.type === "symbol",
    )?.id;
    map.addLayer({
      id: name,
      type: "raster",
      source: name,
      paint: { "raster-opacity": showDemoSurface ? 0.8 : 0.9, "raster-fade-duration": 0 },
    }, before);
    return () => {
      if (instance.current !== map) return;
      if (map.getLayer(name)) map.removeLayer(name);
      if (map.getSource(name)) map.removeSource(name);
    };
  }, [styleReady, rentColorMode, showDemoSurface, districtPrices, priceRange]);

  // Experimental mode: color actual vector-tile building footprints while
  // leaving the ground, streets, and parks at their default basemap colors.
  // This does not assign a rental price to an individual building.
  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady || rentColorMode !== "buildings" ||
      (!showDemoSurface && (!districtPrices?.length || !priceRange))) return;

    const originalBuildingLayer = map.getStyle().layers?.find(
      (layer) => (layer.type === "fill-extrusion" || layer.type === "fill") &&
        layer["source-layer"] === "building",
    );
    if (!originalBuildingLayer || !("source" in originalBuildingLayer)) return;
    const vectorSource = originalBuildingLayer.source;
    const vectorSourceLayer = "building";
    const sourceId = "fairrent-rent-building-footprints";
    const flatId = "fairrent-rent-building-flat";
    const extrusionId = "fairrent-rent-building-3d";
    const registry = JSON.parse(districtGeojson) as {
      features: Array<{
        geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
        properties: { district_id: string; name: string };
      }>;
    };

    const sampleColor: (longitude: number, latitude: number) => string | null = showDemoSurface
      ? (longitude, latitude) => {
          const [west, south, east, north] = DEMO_SURFACE.bounds;
          const observed = demoRentValue(
            (longitude - west) / (east - west),
            (north - latitude) / (north - south),
          );
          return observed === null
            ? null
            : rentGradientColor((observed - DEMO_SURFACE.minimum) /
                (DEMO_SURFACE.maximum - DEMO_SURFACE.minimum));
        }
      : createBuildingRentSampler(
          registry.features,
          new globalThis.Map((districtPrices ?? []).map((item) => [item.districtId, item])),
          priceRange!,
        );

    map.addSource(sourceId, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    const beforeSymbols = map.getStyle().layers?.find((layer) => layer.type === "symbol")?.id;
    map.addLayer({
      id: flatId,
      type: "fill",
      source: sourceId,
      paint: {
        "fill-color": ["get", "rentColor"],
        "fill-opacity": 0.94,
        "fill-outline-color": "#334155",
      },
    }, beforeSymbols);
    map.addLayer({
      id: extrusionId,
      type: "fill-extrusion",
      source: sourceId,
      paint: {
        "fill-extrusion-color": ["get", "rentColor"],
        "fill-extrusion-base": 0,
        "fill-extrusion-height": ["get", "buildingHeight"],
        "fill-extrusion-opacity": 0.94,
      },
    }, beforeSymbols);

    let disposed = false;
    let pending: number | undefined;
    const update = () => {
      if (disposed || instance.current !== map || !map.getSource(vectorSource)) return;
      const visible = map.querySourceFeatures(vectorSource, { sourceLayer: vectorSourceLayer });
      const features = [];
      // Tile-clipped footprints may repeat; their coloring is still location-based.
      for (const feature of visible) {
        if (feature.geometry.type !== "Polygon" && feature.geometry.type !== "MultiPolygon") continue;
        const center = footprintCenter(feature.geometry);
        if (!center) continue;
        const color = sampleColor(center[0], center[1]);
        if (!color) continue;
        const rawHeight = Number(feature.properties?.["render_height"] ?? feature.properties?.["height"] ?? 10);
        const buildingHeight = Number.isFinite(rawHeight)
          ? Math.max(3, Math.min(160, rawHeight)) : 10;
        features.push({
          type: "Feature" as const,
          geometry: feature.geometry,
          properties: { rentColor: color, buildingHeight },
        });
      }
      const colored = map.getSource(sourceId) as GeoJSONSource | undefined;
      if (colored) void colored.setData({ type: "FeatureCollection", features });
    };
    const schedule = () => {
      if (disposed || pending !== undefined) return;
      pending = window.setTimeout(() => {
        pending = undefined;
        update();
      }, 180);
    };
    const moved = map.on("moveend", schedule);
    const sourceChanged = map.on("sourcedata", (event) => {
      if (event.sourceId === vectorSource) schedule();
    });
    schedule();
    return () => {
      disposed = true;
      if (pending !== undefined) window.clearTimeout(pending);
      moved.unsubscribe();
      sourceChanged.unsubscribe();
      if (instance.current !== map) return;
      if (map.getLayer(extrusionId)) map.removeLayer(extrusionId);
      if (map.getLayer(flatId)) map.removeLayer(flatId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    };
  }, [styleReady, districtPrices, priceRange, showDemoSurface, rentColorMode]);

  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady) return;

    const buildings = map
      .getStyle()
      .layers?.filter(
        (layer) => layer.type === "fill-extrusion" && layer["source-layer"] === "building",
      );

    if (!buildings?.length) return;

    const buildingLayer = buildings[0];
    if (!buildingLayer || buildingLayer.type !== "fill-extrusion") return;

    const flatBuildingsId = "fairrent-flat-buildings";

    if (!map.getLayer(flatBuildingsId)) {
      map.addLayer(
        {
          id: flatBuildingsId,
          type: "fill",
          source: buildingLayer.source,
          "source-layer": "building",
          minzoom: buildingLayer.minzoom ?? 14,
          paint: {
            "fill-color": "#e2e8f0",
            "fill-outline-color": "#94a3b8",
            "fill-opacity": 0.7,
          },
        },
        buildingLayer.id,
      );
    }

    map.setLayoutProperty(flatBuildingsId, "visibility", rentColorMode === "ground" && viewMode === "2d" ? "visible" : "none");
    if (map.getLayer("fairrent-rent-building-flat")) {
      map.setLayoutProperty("fairrent-rent-building-flat", "visibility", viewMode === "2d" ? "visible" : "none");
    }
    if (map.getLayer("fairrent-rent-building-3d")) {
      map.setLayoutProperty("fairrent-rent-building-3d", "visibility", viewMode === "3d" ? "visible" : "none");
    }

    for (const layer of buildings) {
      map.setLayoutProperty(layer.id, "visibility", rentColorMode === "ground" && viewMode === "3d" ? "visible" : "none");
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    map.easeTo({
      pitch: viewMode === "3d" ? 55 : 0,
      ...(viewMode === "3d" ? { zoom: Math.max(map.getZoom(), 15) } : {}),
      duration: reducedMotion ? 0 : 600,
    });
  }, [viewMode, styleReady, districtPrices, priceRange, showDemoSurface, rentColorMode]);

  useEffect(() => {
    const bounds = parseMapBounds(bbox);
    if (bounds)
      instance.current?.fitBounds(
        [
          [bounds[0], bounds[1]],
          [bounds[2], bounds[3]],
        ],
        { padding: 0, duration: 0 },
      );
  }, [bbox]);

  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady || !clustered) return;
    const source = "rental-locations";
    const clusters = "rental-clusters";
    const labels = "rental-cluster-count";
    const individual = "rental-points";
    map.addSource(source, {
      type: "geojson",
      cluster: true,
      clusterMaxZoom: 16,
      data: {
        type: "FeatureCollection",
        features: points.map(({ id, longitude, latitude }) => ({
          type: "Feature",
          geometry: { type: "Point", coordinates: [longitude, latitude] },
          properties: { id },
        })),
      },
    });
    map.addLayer({
      id: clusters,
      source,
      type: "circle",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": "#294aaf",
        "circle-radius": ["step", ["get", "point_count"], 15, 100, 20, 1000, 25],
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: labels,
      source,
      type: "symbol",
      filter: ["has", "point_count"],
      layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
      paint: { "text-color": "#fff" },
    });
    map.addLayer({
      id: individual,
      source,
      type: "circle",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": "#294aaf",
        "circle-radius": 6,
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 2,
      },
    });
    const clusterClick = map.on("click", clusters, (event) => {
      const feature = event.features?.[0];
      if (feature?.geometry.type !== "Point") return;
      const clusterId = Number(feature.properties["cluster_id"]);
      const [longitude, latitude] = feature.geometry.coordinates;
      if (longitude === undefined || latitude === undefined) return;
      void (map.getSource(source) as GeoJSONSource)
        .getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          if (instance.current === map && map.getLayer(clusters)) {
            map.easeTo({ center: [longitude, latitude], zoom });
          }
        })
        .catch(() => undefined);
    });
    const pointClick = map.on("click", individual, (event) => {
      const ids = [
        ...new Set((event.features ?? []).map((feature) => String(feature.properties["id"]))),
      ];
      if (ids.length > 1) onOverlap?.(ids);
      else if (ids[0]) onSelect?.(ids[0]);
    });
    return () => {
      clusterClick.unsubscribe();
      pointClick.unsubscribe();
      if (instance.current !== map) return;
      for (const layer of [labels, individual, clusters]) {
        if (map.getLayer(layer)) map.removeLayer(layer);
      }
      if (map.getSource(source)) map.removeSource(source);
    };
  }, [clustered, onOverlap, onSelect, points, styleReady]);

  useEffect(() => {
    const map = instance.current;
    if (!map || clustered) return;
    const markers = points.map((point) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rental-map-marker";
      button.dataset["rentalId"] = point.id;
      button.title = point.label;
      button.setAttribute(
        "aria-label",
        `${point.label}${point.approximate ? ", approximate location" : ""}. Show rental preview`,
      );
      markerButtons.current.push(button);
      button.addEventListener("click", () => onSelect?.(point.id));
      return new Marker({ element: button, anchor: "center" })
        .setLngLat([point.longitude, point.latitude])
        .addTo(map);
    });
    return () => {
      markers.forEach((marker) => marker.remove());
      markerButtons.current = [];
    };
  }, [clustered, points, onSelect]);

  useEffect(() => {
    const map = instance.current;
    if (!map || !pickedCoordinate) return;
    const marker = document.createElement("div");
    marker.className = "rental-map-marker";
    marker.title = "Selected assessment location";
    marker.setAttribute("role", "img");
    marker.setAttribute("aria-label", "Selected assessment location");
    const point = new Marker({ element: marker, anchor: "center" })
      .setLngLat([pickedCoordinate.longitude, pickedCoordinate.latitude])
      .addTo(map);
    return () => { point.remove(); };
  }, [pickedCoordinate]);

  useEffect(() => {
    const map = instance.current;
    if (!map) return;
    const markers = places.map((place) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `map-place-marker map-place-${place.type}`;
      button.dataset["placeId"] = place.id;
      button.textContent = place.type === "metro" ? "M" : "U";
      button.title = place.name;
      button.setAttribute(
        "aria-label",
        `${place.type === "metro" ? "Metro station" : "University"}: ${place.name}. Show place`,
      );
      button.addEventListener("click", () => onSelectPlace?.(place.id));
      placeButtons.current.push(button);
      return new Marker({ element: button, anchor: "center" })
        .setLngLat([place.longitude, place.latitude])
        .addTo(map);
    });
    return () => {
      markers.forEach((marker) => marker.remove());
      placeButtons.current = [];
    };
  }, [places, onSelectPlace]);

  useEffect(() => {
    for (const button of placeButtons.current) {
      const selected = button.dataset["placeId"] === selectedPlaceId;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    }
  }, [places, selectedPlaceId]);

  useEffect(() => {
    for (const button of markerButtons.current) {
      const selected = button.dataset["rentalId"] === selectedId;
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    }
  }, [points, selectedId]);

  return (
    <section
      className={`map-canvas ${expanded ? "map-canvas-expanded" : ""}`}
      aria-label="Interactive map of Yerevan"
    >
      {/* Inline positioning prevents unlayered vendor CSS overriding Tailwind positioning. */}
      <div
        ref={container}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      />

      {loading && !error && (
        <p role="status" className="map-notice map-notice-loading">
          <span className="map-loading-dot" aria-hidden="true" />
          Loading Yerevan…
        </p>
      )}
      {error && (
        <p role="status" className="map-notice map-notice-error">
          {error}
        </p>
      )}
    </section>
  );
}
