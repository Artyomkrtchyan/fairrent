import { useEffect, useRef, useState } from "react";
import { Map, NavigationControl, AttributionControl, Marker, setWorkerUrl } from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";

setWorkerUrl(mapWorkerUrl);

export interface RentalMapPoint {
  id: string;
  longitude: number;
  latitude: number;
  label: string;
  approximate: boolean;
}

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
  points?: readonly RentalMapPoint[];
  selectedId?: string | undefined;
  onSelect?: (id: string) => void;
  expanded?: boolean;
  camera?: MapCamera;
  onCameraChange?: (camera: MapCamera) => void;
}

export function MapCanvas({
  expanded = false,
  camera,
  onCameraChange,
  points = EMPTY_POINTS,
  selectedId,
  onSelect,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<Map | null>(null);
  const markerButtons = useRef<HTMLButtonElement[]>([]);
  const initialOptions = useRef({ expanded, camera: camera ?? DEFAULT_CAMERA });
  const cameraCallback = useRef(onCameraChange);
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
        // Scrolling over the embedded map should move the page, not zoom the map.
        scrollZoom: options.expanded,
        cooperativeGestures: !options.expanded,
      });
      instance.current = map;

      map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
      map.addControl(new AttributionControl({ compact: true }), "bottom-right");

      const activeMap = map;
      map.on("moveend", () => {
        if (disposed) return;
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

  useEffect(() => {
    const map = instance.current;
    if (!map) return;
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
  }, [points, onSelect]);

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
