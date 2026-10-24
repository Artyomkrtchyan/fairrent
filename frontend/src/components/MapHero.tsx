import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type KeyboardEvent,
} from "react";
import { ArrowDown, ArrowUpRight, Expand, MapPin, X } from "lucide-react";
import { parseMapBounds, serializeMapBounds, type MapBounds } from "@/lib/map-bounds";
import { Link } from "@tanstack/react-router";
import { usePrefs } from "@/lib/prefs";
import { apiMode } from "@/api/client";
import { hasMapCoordinates, type MapListing } from "@/lib/map-listings";
import type { MapCamera } from "@/components/MapCanvas";

const MapCanvas = lazy(() =>
  import("@/components/MapCanvas").then((module) => ({ default: module.MapCanvas })),
);

const INITIAL_CAMERA: MapCamera = {
  center: [44.51562, 40.17767],
  zoom: 13,
  pitch: 0,
  bearing: 0,
};

const NO_LISTINGS: readonly MapListing[] = [];

export function MapHero({
  bbox,
  onSearchArea,
  listings = NO_LISTINGS,
  pending = false,
  failed = false,
  hasMore = false,
}: {
  bbox?: string | undefined;
  onSearchArea?: (bbox: string) => void;
  listings?: readonly MapListing[];
  pending?: boolean;
  failed?: boolean;
  hasMore?: boolean;
}) {
  const { format } = usePrefs();
  const showDemoSurface = apiMode === "mock";
  const [viewport, setViewport] = useState<MapBounds>();
  const viewportBbox = viewport ? serializeMapBounds(viewport) : undefined;
  const validArea = parseMapBounds(viewportBbox);
  const areaSearch = onSearchArea && (
    <div className="map-area-search">
      <button
        type="button"
        className="map-expand-button"
        disabled={pending || !validArea || viewportBbox === bbox}
        onClick={() => {
          if (viewportBbox && validArea) onSearchArea(viewportBbox);
        }}
      >
        {pending ? "Searching…" : "Search this area"}
      </button>
    </div>
  );
  const areaStatus =
    viewport && !validArea
      ? "Zoom in to search a smaller area."
      : bbox && viewportBbox !== bbox
        ? "Map moved — search to update rental dots."
        : bbox
          ? "Rental dots show your searched area."
          : "Search this area to show available rentals.";
  const gradientLegend = (
    <aside className="map-price-legend" aria-label="Area rent colour legend">
      <p className="map-demo-label">
        {showDemoSurface ? "Synthetic design preview" : "Area price layer unavailable"}
      </p>
      {showDemoSurface && (
        <>
          <h3>Monthly asking rent / m²</h3>
          <div className="map-price-ramp" aria-hidden="true" />
          <div className="map-price-ticks">
            <span>6</span>
            <span>12</span>
            <span>18</span>
            <span>24</span>
          </div>
          <p>USD / m² / month · Lower → Higher</p>
          <p>Invented values, not market estimates.</p>
          <p>
            <span className="map-no-data-key" /> Outside demo extent: no data
          </p>
        </>
      )}
    </aside>
  );
  const [selectedId, setSelectedId] = useState<string>();
  const points = useMemo(
    () =>
      listings.filter(hasMapCoordinates).map((listing) => ({
        id: listing.id,
        longitude: listing.longitude!,
        latitude: listing.latitude!,
        label:
          listing.price_monthly_normalized === null
            ? "Rent unavailable"
            : format(listing.price_monthly_normalized),
        approximate: listing.coordinate_confidence === "approximate",
      })),
    [listings, format],
  );
  const selected = listings.find(
    (listing) => listing.id === selectedId && hasMapCoordinates(listing),
  );
  const markerProps = {
    points: bbox ? points : [],
    showDemoSurface,
    selectedId,
    onSelect: setSelectedId,
    bbox,
  };
  const coverage = pending
    ? "Loading rental locations…"
    : failed
      ? "Rental locations unavailable. Try again in the catalogue below."
      : !bbox
        ? "Rental results are also available in the catalogue below."
        : `${points.length} of ${listings.length} rentals on this results page have usable locations.${hasMore ? " More results are available in the catalogue." : ""}`;
  const preview = bbox && selected && (
    <section className="rental-map-preview" aria-label="Selected rental" aria-live="polite">
      <button
        type="button"
        className="rental-preview-close"
        aria-label="Close rental preview"
        onClick={() => setSelectedId(undefined)}
      >
        <X size={18} />
      </button>
      <h3>{selected.title || "Apartment in Yerevan"}</h3>
      <p className="rental-preview-price">
        {selected.price_monthly_normalized === null
          ? "Rent unavailable"
          : `${format(selected.price_monthly_normalized)} / month`}
      </p>
      <p>
        {selected.rooms === null ? "Rooms unavailable" : `${selected.rooms} rooms`} ·{" "}
        {selected.area_sqm === null ? "Area unavailable" : `${selected.area_sqm} m²`}
      </p>
      <p>
        {selected.coordinate_confidence === "approximate"
          ? "Approximate location — not an exact building."
          : "Source-reported location."}
      </p>
      {apiMode === "mock" && <p>Synthetic example</p>}
      {selected.freshness.is_stale && <p>Source data is marked stale.</p>}
      <Link to="/listings/$id" params={{ id: selected.id }} state={{ fromCatalogue: true }}>
        View details →
      </Link>
    </section>
  );
  const [expanded, setExpanded] = useState(false);
  const [expandedCamera, setExpandedCamera] = useState(INITIAL_CAMERA);
  const [returnedCamera, setReturnedCamera] = useState(INITIAL_CAMERA);
  const latestCamera = useRef(INITIAL_CAMERA);
  const expandButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  const rememberCamera = useCallback((camera: MapCamera) => {
    latestCamera.current = camera;
  }, []);

  function closeMap() {
    setReturnedCamera(latestCamera.current);
    setExpanded(false);
  }

  useEffect(() => {
    if (!expanded || !dialog.current) return;
    const modal = dialog.current;
    const trigger = expandButton.current;
    const scrollPosition = { top: window.scrollY, left: window.scrollX };
    const previousOverflow = document.body.style.overflow;
    modal.showModal();
    document.body.style.overflow = "hidden";

    return () => {
      if (modal.open) modal.close();
      document.body.style.overflow = previousOverflow;
      trigger?.focus({ preventScroll: true });
      window.scrollTo({ ...scrollPosition, behavior: "instant" });
    };
  }, [expanded]);

  function keepFocusInMap(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;
    const modal = event.currentTarget;
    const controls = [
      ...modal.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      ),
    ].filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) {
      event.preventDefault();
      modal.focus();
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function browseRentals(event: MouseEvent<HTMLAnchorElement>) {
    const catalogue = document.getElementById("rental-catalogue");
    if (!catalogue) return;
    event.preventDefault();
    catalogue.focus({ preventScroll: true });
    catalogue.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
      block: "start",
    });
  }

  return (
    <section id="map-explore" className="map-hero" aria-labelledby="map-hero-title" tabIndex={-1}>
      <div className="map-hero-inner">
        <div className="map-hero-heading">
          <div>
            <p className="map-hero-eyebrow">
              <span aria-hidden="true" /> Yerevan, Armenia · Long-term rentals
            </p>
            <h1 id="map-hero-title">A clearer view of your next home.</h1>
            <p className="map-hero-intro">Explore Yerevan. Find your next home.</p>
          </div>
          <a className="map-browse-button" href="#rental-catalogue" onClick={browseRentals}>
            Browse rentals <ArrowDown size={17} aria-hidden="true" />
          </a>
        </div>

        <div className="map-frame">
          <div className="map-frame-toolbar">
            <div className="map-frame-place">
              <span className="map-place-icon">
                <MapPin size={19} aria-hidden="true" />
              </span>
              <div>
                <h2>Explore Yerevan</h2>
                <p>Find your bearings before your next home.</p>
              </div>
            </div>
            <div className="map-toolbar-actions">
              {areaSearch}
              <button
                ref={expandButton}
                type="button"
                onClick={() => {
                  setExpandedCamera(latestCamera.current);
                  setExpanded(true);
                }}
                className="map-expand-button"
                aria-haspopup="dialog"
              >
                <Expand size={16} aria-hidden="true" />
                <span>Expand map</span>
              </button>
            </div>
          </div>

          <div className="rental-map-stage">
            <Suspense
              fallback={
                <div className="map-canvas">
                  <p role="status" className="map-notice map-notice-loading">
                    Preparing the map…
                  </p>
                </div>
              }
            >
              <MapCanvas
                onBoundsChange={expanded ? undefined : setViewport}
                camera={returnedCamera}
                onCameraChange={rememberCamera}
                {...markerProps}
              />
            </Suspense>
            {!expanded && gradientLegend}
            {!expanded && preview}
          </div>
          <p className="rental-map-coverage" role="status">
            {areaStatus} {coverage}
          </p>

          <div className="map-frame-footer">
            <p>Scroll to keep browsing. Use + / − to zoom the map.</p>
            <a href="#rental-catalogue" onClick={browseRentals}>
              Find a rental <ArrowUpRight size={15} aria-hidden="true" />
            </a>
          </div>
        </div>
        <p className="map-hero-caption">A city to explore. A place to call home.</p>
      </div>

      <dialog
        ref={dialog}
        className="map-fullscreen"
        onKeyDown={keepFocusInMap}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onCancel={(event) => {
          event.preventDefault();
          closeMap();
        }}
        onClose={() => {
          if (expanded) closeMap();
        }}
      >
        {expanded && (
          <>
            <div className="map-fullscreen-toolbar">
              <div>
                <h2 id={titleId}>Explore Yerevan</h2>
                <p id={descriptionId}>
                  Drag to explore and use the wheel to zoom. Close or press Escape to return to your
                  search.
                </p>
              </div>
              <div className="map-toolbar-actions">
                {areaSearch}
                <button type="button" className="map-expand-button" onClick={closeMap}>
                  <X size={18} aria-hidden="true" /> Close map
                </button>
              </div>
            </div>
            <div className="map-fullscreen-body">
              <Suspense
                fallback={
                  <p role="status" className="p-5">
                    Preparing the map…
                  </p>
                }
              >
                <MapCanvas
                  expanded
                  onBoundsChange={setViewport}
                  camera={expandedCamera}
                  onCameraChange={rememberCamera}
                  {...markerProps}
                  bbox={undefined}
                />
              </Suspense>
              {gradientLegend}
              {preview}
              <p className="rental-map-coverage rental-map-coverage-expanded" role="status">
                {areaStatus} {coverage}
              </p>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}
