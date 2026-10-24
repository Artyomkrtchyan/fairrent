import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type MouseEvent,
  type KeyboardEvent,
} from "react";
import { ArrowDown, ArrowUpRight, Expand, MapPin, X } from "lucide-react";
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

export function MapHero() {
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

          <Suspense
            fallback={
              <div className="map-canvas">
                <p role="status" className="map-notice map-notice-loading">
                  Preparing the map…
                </p>
              </div>
            }
          >
            <MapCanvas camera={returnedCamera} onCameraChange={rememberCamera} />
          </Suspense>

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
                <MapCanvas expanded camera={latestCamera.current} onCameraChange={rememberCamera} />
              </Suspense>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}
