import { useEffect, useRef, useState } from "react";
import {
  Map,
  NavigationControl,
  AttributionControl,
  Marker,
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
import { createBuildingRentSampler, footprintCenter, nearestBuildingRentColorIndex, rentGradientColor } from "@/lib/map-building-rent-colors";

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
  /** Colorful, noninteractive house symbols for zoom levels without building geometry. */
  buildingLocations?: readonly RentalMapPoint[];
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
  buildingLocations = EMPTY_POINTS,
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

  // At citywide zoom, the basemap omits individual building polygons. Display
  // small building-shaped symbols AT KNOWN RENTAL LOCATIONS, not a colored ground
  // layer or fabricated footprints. At zoom >= 14, the vector footprints take
  // over. Symbol collision keeps the overview legible and fast.
  useEffect(() => {
    const map = instance.current;
    if (!map || !styleReady || rentColorMode !== "buildings" || !buildingLocations.length ||
      (!showDemoSurface && (!districtPrices?.length || !priceRange))) return;

    const registry = JSON.parse(districtGeojson) as {
      features: Array<{
        geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
        properties: { district_id: string; name: string };
      }>;
    };
    const sampleColor: (longitude: number, latitude: number) => string | null = showDemoSurface
      ? (longitude, latitude) => {
          const [west, south, east, north] = DEMO_SURFACE.bounds;
          const value = demoRentValue(
            (longitude - west) / (east - west),
            (north - latitude) / (north - south),
          );
          return value === null ? null :
            rentGradientColor((value - DEMO_SURFACE.minimum) /
              (DEMO_SURFACE.maximum - DEMO_SURFACE.minimum));
        }
      : createBuildingRentSampler(
          registry.features,
          new globalThis.Map((districtPrices ?? []).map((item) => [item.districtId, item])),
          priceRange!,
        );

    const sourceId = "fairrent-citywide-building-locations";
    const layerId = "fairrent-citywide-building-symbols";
    const iconPrefix = "fairrent-rent-house-";
    const shadeCount = 21;
    const addedImages: string[] = [];

    // A small silhouette with a roof and windows stays recognizable as a house
    // even at low zoom; this is a *rental location* marker, not a roof polygon.
    for (let shade = 0; shade < shadeCount; shade++) {
      const name = `${iconPrefix}${shade}`;
      if (map.hasImage(name)) continue;
      const canvas = document.createElement("canvas");
      canvas.width = 28;
      canvas.height = 30;
      const context = canvas.getContext("2d");
      if (!context) continue;
      context.fillStyle = rentGradientColor(shade / (shadeCount - 1));
      context.strokeStyle = "#27344d";
      context.lineWidth = 1.8;
      context.beginPath();
      context.moveTo(2, 13);
      context.lineTo(14, 3);
      context.lineTo(26, 13);
      context.closePath();
      context.fill();
      context.stroke();
      context.fillRect(5, 13, 18, 14);
      context.strokeRect(5, 13, 18, 14);
      context.fillStyle = "#f8fafc";
      context.fillRect(10, 17, 4, 5);
      context.fillRect(17, 17, 4, 5);
      map.addImage(name, context.getImageData(0, 0, canvas.width, canvas.height), { pixelRatio: 2 });
      addedImages.push(name);
    }

    const features = buildingLocations.flatMap((point) => {
      if (!Number.isFinite(point.longitude) || !Number.isFinite(point.latitude)) return [];
      const color = sampleColor(point.longitude, point.latitude);
      if (!color) return [];
      return [{
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [point.longitude, point.latitude],
        },
        properties: { shade: nearestBuildingRentColorIndex(color, shadeCount) },
      }];
    });

    map.addSource(sourceId, {
      type: "geojson",
      data: { type: "FeatureCollection", features },
    });
    const beforeLabels = map.getStyle().layers?.find((layer) => layer.type === "symbol")?.id;
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      minzoom: 7,
      maxzoom: 15,
      layout: {
        "icon-image": ["concat", iconPrefix, ["to-string", ["get", "shade"]]],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.7, 12, 1.1, 14.9, 0.7],
        "icon-allow-overlap": false,
        "icon-padding": 0,
      },
    }, beforeLabels);

    return () => {
      if (instance.current !== map) return;
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      for (const name of addedImages) {
        if (map.hasImage(name)) map.removeImage(name);
      }
    };
  }, [styleReady, rentColorMode, showDemoSurface, districtPrices, priceRange, buildingLocations]);

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
      minzoom: 15,
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
      minzoom: 15,
      source: sourceId,
      paint: {
        "fill-extrusion-color": ["get", "rentColor"],
        "fill-extrusion-base": 0,
        "fill-extrusion-height": ["get", "buildingHeight"],
        "fill-extrusion-opacity": 0.94,
      },
    }, beforeSymbols);

    // Heavy tile-to-GeoJSON conversion must NEVER run during a pan/zoom.
    // "idle" fires after the camera settles and tiles finish loading.
    // Keep MapLibre's native vector basemap responsive throughout movement.
    let disposed = false;
    let pending: number | undefined;
    let lastUpdateKey = "";
    let lastSourcesSignature = "";
    const MAX_VISIBLE_BUILDINGS = 1200;

    const update = () => {
      if (disposed || instance.current !== map || !map.getSource(vectorSource)) return;
      if (map.getZoom() < 15 || map.isMoving()) return;
      const bounds = map.getBounds();
      const signature = [
        Math.round(map.getZoom() * 3),
        bounds.getWest().toFixed(3), bounds.getSouth().toFixed(3),
        bounds.getEast().toFixed(3), bounds.getNorth().toFixed(3),
      ].join(":");
      const visible = map.querySourceFeatures(vectorSource, { sourceLayer: vectorSourceLayer });
      const features = [];
      const seen = new Set<string>();
      // Filter cached/offscreen vector-tile features BEFORE geometry processing.
      // Once a dense street has enough detail, favor smooth scrolling over
      // synchronously converting thousands of additional buildings.
      for (const feature of visible) {
        if (feature.geometry.type !== "Polygon" && feature.geometry.type !== "MultiPolygon") continue;
        const center = footprintCenter(feature.geometry);
        if (!center) continue;
        if (center[0] < bounds.getWest() || center[0] > bounds.getEast() ||
            center[1] < bounds.getSouth() || center[1] > bounds.getNorth()) continue;
        const key = feature.id === undefined
          ? `${center[0].toFixed(5)}:${center[1].toFixed(5)}`
          : String(feature.id);
        if (seen.has(key)) continue;
        seen.add(key);
        const color = sampleColor(center[0], center[1]);
        if (!color) continue;
        const rawHeight = Number(feature.properties?.["render_height"] ?? feature.properties?.["height"] ?? 10);
        const buildingHeight = Number.isFinite(rawHeight) ? Math.max(3, Math.min(160, rawHeight)) : 10;
        features.push({
          type: "Feature" as const,
          geometry: feature.geometry,
          properties: { rentColor: color, buildingHeight },
        });
        if (features.length >= MAX_VISIBLE_BUILDINGS) break;
      }
      // A source update can itself cause another idle event. Avoid that loop,
      // but allow genuinely new tile data at the same viewport to render.
      const sourceSignature = `${features.length}:${features.slice(0, 4).map((item) =>
        item.geometry.coordinates.length).join(",")}`;
      if (signature === lastUpdateKey && sourceSignature === lastSourcesSignature) return;
      lastUpdateKey = signature;
      lastSourcesSignature = sourceSignature;
      const source = map.getSource(sourceId) as GeoJSONSource | undefined;
      if (source) void source.setData({ type: "FeatureCollection", features });
    };

    const schedule = () => {
      if (disposed || pending !== undefined) return;
      pending = window.setTimeout(() => {
        pending = undefined;
        update();
      }, 90);
    };
    const idle = map.on("idle", schedule);
    // When the layer is installed after the map is already idle, trigger once.
    schedule();
    return () => {
      disposed = true;
      if (pending !== undefined) window.clearTimeout(pending);
      idle.unsubscribe();
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
