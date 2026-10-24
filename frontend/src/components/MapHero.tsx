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
  listings = NO_LISTINGS,
  pending = false,
  failed = false,
  hasMore = false,
}: {
  listings?: readonly MapListing[];
  pending?: boolean;
  failed?: boolean;
  hasMore?: boolean;
}) {
  const { format } = usePrefs();
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
  const markerProps = { points, selectedId, onSelect: setSelectedId };
  const coverage = pending
    ? "Loading rental locations…"
    : failed
      ? "Rental locations unavailable. Try again in the catalogue below."
      : `${points.length} of ${listings.length} rentals on this results page have usable locations.${hasMore ? " More results are available in the catalogue." : ""}`;
  const preview = selected && (
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
            <h1 id="map-hero-title">
              A clearer view of
              <br className="hidden sm:block" /> your next home.
            </h1>
            <p className="map-hero-intro">
              Start with the city. Find your neighborhood.
              <br className="hidden sm:block" /> Explore rentals with a little more perspective.
            </p>
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
            <button
              ref={expandButton}
              type="button"
              onClick={() => setExpanded(true)}
              className="map-expand-button"
              aria-haspopup="dialog"
            >
              <Expand size={16} aria-hidden="true" />
              <span>Expand map</span>
            </button>
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
              <MapCanvas camera={returnedCamera} onCameraChange={rememberCamera} {...markerProps} />
            </Suspense>
            {!expanded && preview}
          </div>
          <p className="rental-map-coverage" role="status">
            {coverage}
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
              <button type="button" className="map-expand-button" onClick={closeMap}>
                <X size={18} aria-hidden="true" /> Close map
              </button>
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
                  camera={latestCamera.current}
                  onCameraChange={rememberCamera}
                  {...markerProps}
                />
              </Suspense>
              {preview}
              <p className="rental-map-coverage rental-map-coverage-expanded" role="status">
                {coverage}
              </p>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}
