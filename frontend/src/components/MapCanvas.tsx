import { useEffect, useRef, useState } from "react";

import {
  Map,
  NavigationControl,
  AttributionControl,
  setWorkerUrl,
} from "maplibre-gl";

import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

import "maplibre-gl/dist/maplibre-gl.css";

setWorkerUrl(mapWorkerUrl);

const DEFAULT_STYLE =
  "https://tiles.openfreemap.org/styles/liberty";

export function MapCanvas() {
  const container = useRef<HTMLDivElement>(null);

  const [headerHeight, setHeaderHeight] = useState(84);

useEffect(() => {
  const header = document.querySelector("header");

  if (!header) return;

  const measureHeader = () => {
    setHeaderHeight(header.getBoundingClientRect().height);
  };

  measureHeader();

  const observer = new ResizeObserver(measureHeader);
  observer.observe(header);

  return () => observer.disconnect();
}, []);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!container.current) return;

    let map: Map | undefined;
    let observer: ResizeObserver | undefined;
    let disposed = false;

    const timeout = window.setTimeout(() => {
      if (!disposed) {
        setLoading(false);
        setError(
          "The map is taking too long to load. You can still browse the listings.",
        );
      }
    }, 20_000);

    try {
      map = new Map({
        container: container.current,
        style:
          import.meta.env["VITE_MAP_STYLE_URL"] ||
          DEFAULT_STYLE,

        // Republic Square, Yerevan.
        center: [44.51562, 40.17767],
        zoom: 13,
        pitch: 0,
        bearing: 0,

        attributionControl: false,
      });

      map.addControl(
        new NavigationControl({
          visualizePitch: true,
        }),
        "top-right",
      );

      map.addControl(
        new AttributionControl({
          compact: true,
        }),
        "bottom-right",
      );

      map.once("load", () => {
        if (disposed) return;

        window.clearTimeout(timeout);
        setLoading(false);
        setError(null);
      });

      map.on("error", () => {
        if (disposed) return;

        setError(
          "Some map content could not load. Check your connection; listings remain available.",
        );
      });

      const activeMap = map;

      observer = new ResizeObserver(() => {
        activeMap.resize();
      });

      observer.observe(container.current);
    } catch {
      window.clearTimeout(timeout);

      if (!disposed) {
        setLoading(false);
        setError(
          "The map could not start in this browser. Listings remain available.",
        );
      }
    }

    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      observer?.disconnect();
      map?.remove();
    };
  }, []);

  return (
   <section
  className="relative isolate overflow-hidden border-b bg-muted"
  style={{
    height: `calc(100dvh - ${headerHeight}px)`,
    minHeight: "280px",
  }}
  aria-label="Interactive map of Yerevan"
>
    <div
  ref={container}
  style={{
    position: "absolute",
    inset: 0,
    width: "100%",
    height: "100%",
  }}
/>

      {loading && !error && (
        <p
          role="status"
          className="absolute left-4 top-4 z-10 rounded-lg border bg-card px-4 py-3 text-sm shadow"
        >
          Loading Yerevan map…
        </p>
      )}

      {error && (
        <p
          role="status"
          className="absolute bottom-12 left-4 right-4 z-10 rounded-lg border bg-card px-4 py-3 text-sm shadow"
        >
          {error}
        </p>
      )}
    </section>
  );
}