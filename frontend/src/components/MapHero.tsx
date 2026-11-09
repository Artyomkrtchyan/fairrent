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
import { ArrowDown, Expand, MapPin, X } from "lucide-react";
import { parseMapBounds, serializeMapBounds, type MapBounds } from "@/lib/map-bounds";
import { useInfrastructure, hasInfrastructureCoordinates } from "@/api/infrastructure";
import { Link } from "@tanstack/react-router";
import { usePrefs } from "@/lib/prefs";
import { apiMode } from "@/api/client";
import { hasMapCoordinates, type MapListing } from "@/lib/map-listings";
import type { MapCamera } from "@/components/MapCanvas";
import { useQuery } from "@tanstack/react-query";
import { getListingDetails, getListings, type ListingMapPoint } from "@/api/listings";
import { getMarketIndex, type MarketIndex } from "@/api/market";
import { summarizeDistrictPrices } from "@/lib/district-price-layer";
import { snapshotMapPrices } from "@/lib/map-listing-price-snapshot";

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
  onClearArea,
  listings = NO_LISTINGS,
  pending = false,
  failed = false,
  hasMore = false,
  mapLocations,
  onRetry,
}: {
  bbox?: string | undefined;
  onSearchArea?: (bbox: string) => void;
  onClearArea?: () => void;
  listings?: readonly MapListing[];
  pending?: boolean;
  failed?: boolean;
  hasMore?: boolean;
  mapLocations?: readonly ListingMapPoint[] | undefined;
  onRetry?: () => void;
}) {
  const { format } = usePrefs();
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d");

  const viewModeControls = (
    <div role="group" aria-label="Map view" className="map-view-toggle">
      <button
        type="button"
        className="map-expand-button"
        aria-pressed={viewMode === "2d"}
        onClick={() => setViewMode("2d")}
      >
        2D
      </button>
      <button
        type="button"
        className="map-expand-button"
        aria-pressed={viewMode === "3d"}
        onClick={() => setViewMode("3d")}
      >
        3D
      </button>
    </div>
  );
  const showDemoSurface = apiMode === "mock";
  const [viewport, setViewport] = useState<MapBounds>();
  const viewportBbox = viewport ? serializeMapBounds(viewport) : undefined;
  const validArea = parseMapBounds(viewportBbox);
  const [showMetro, setShowMetro] = useState(true);
  const [showUniversities, setShowUniversities] = useState(true);
  const [showDistrictPrices, setShowDistrictPrices] = useState(true);
  const districtQuery = useQuery({
    queryKey: ["map-district-median-prices", apiMode],
    enabled: apiMode === "real" && showDistrictPrices,
    retry: false,
    staleTime: 5 * 60 * 1000,
    queryFn: async ({ signal }): Promise<MarketIndex[]> => {
      // Query up to 180 days of published index history, without inventing prices.\n      // Older observations are visibly labelled rather than presented as current.
      const period_start = new Date(Date.now() - 180 * 24 * 60 * 60 * 1000)
        .toISOString().slice(0, 10);
      const all: MarketIndex[] = [];
      for (let page = 1; page <= 12; page++) {
        const result = await getMarketIndex({ period_start, page_size: 100, page }, signal);
        all.push(...result.items);
        if (!result.has_more) return all;
      }
      throw new Error("The district price history exceeds the supported page limit.");
    },
  });
  const districtSummary = useMemo(
    () => summarizeDistrictPrices(districtQuery.data ?? []),
    [districtQuery.data],
  );
  const weeklySupported = districtSummary.latest.length > 0;
  const snapshotQuery = useQuery({
    queryKey: ["map-listing-rent-price-snapshot", apiMode],
    enabled: apiMode === "real" && showDistrictPrices &&
      !districtQuery.isPending && (districtQuery.isError || !weeklySupported),
    retry: false,
    staleTime: 5 * 60 * 1000,
    queryFn: async ({ signal }) => {
      const listings: Awaited<ReturnType<typeof getListings>>["items"] = [];
      let total = 0;
      let hasMore = false;
      const maximumPages = 15;
      for (let page = 1; page <= maximumPages; page++) {
        const result = await getListings(signal, {
          page,
          page_size: 100,
          status: "active",
          sort: "newest",
        });
        listings.push(...result.items);
        total = result.total;
        hasMore = result.has_more;
        if (!result.has_more) break;
      }
      return { listings, total, truncated: hasMore };
    },
  });
  const snapshotSummary = useMemo(
    () => snapshotMapPrices(snapshotQuery.data?.listings ?? []),
    [snapshotQuery.data],
  );
  const useSnapshot = !weeklySupported && snapshotSummary.districtPrices.length > 0;
  const activePrices = useSnapshot ? snapshotSummary.districtPrices : districtSummary.latest;
  const priceRange = useMemo(() => {
    const minimum = useSnapshot ? snapshotSummary.min : districtSummary.minimum;
    const maximum = useSnapshot ? snapshotSummary.max : districtSummary.maximum;
    return minimum !== null && maximum !== null ? { minimum, maximum } : null;
  }, [useSnapshot, snapshotSummary.min, snapshotSummary.max, districtSummary.minimum, districtSummary.maximum]);
  const [selectedPlaceId, setSelectedPlaceId] = useState<string>();
  const nearby = useInfrastructure(viewportBbox, showMetro, showUniversities);
  const places = useMemo(
    () =>
      !parseMapBounds(viewportBbox) || nearby.isError
        ? []
        : (nearby.data?.pages.flatMap((page) => page.items) ?? []).filter(
            (place) =>
              hasInfrastructureCoordinates(place) &&
              (place.type === "metro" ? showMetro : showUniversities),
          ),
    [viewportBbox, nearby.data, nearby.isError, showMetro, showUniversities],
  );
  const selectedPlace = places.find((place) => place.id === selectedPlaceId);
  const showNearby = showMetro || showUniversities;
  const placeControls = (
    <div className="map-layer-toolbar" aria-label="Nearby place layers">
      <span>Nearby</span>
      <label>
        <input
          type="checkbox"
          checked={showMetro}
          onChange={(event) => setShowMetro(event.target.checked)}
        />{" "}
        <span className="map-layer-symbol">M</span> Metro
      </label>
      <label>
        <input
          type="checkbox"
          checked={showUniversities}
          onChange={(event) => setShowUniversities(event.target.checked)}
        />{" "}
        <span className="map-layer-symbol">U</span> Universities
      </label>
      {apiMode === "real" && (
        <label>
          <input
            type="checkbox"
            checked={showDistrictPrices}
            onChange={(event) => setShowDistrictPrices(event.target.checked)}
          />{" "}
          District rent prices
        </label>
      )}
      {showNearby && (
        <span role="status" className="map-nearby-status">
          {!validArea
            ? "Zoom in to show nearby places."
            : nearby.isError
              ? "Nearby places unavailable."
              : nearby.isPending
                ? "Loading nearby places…"
                : `${places.length} places shown${nearby.hasNextPage ? " · More available" : ""}${apiMode === "mock" ? " · Demo data" : ""}`}
        </span>
      )}
      {showNearby && nearby.isError && (
        <button type="button" onClick={() => void nearby.refetch()}>
          Retry places
        </button>
      )}
      {showNearby && nearby.hasNextPage && (
        <button
          type="button"
          disabled={nearby.isFetchingNextPage}
          onClick={() => void nearby.fetchNextPage()}
        >
          {nearby.isFetchingNextPage ? "Loading…" : "Load more places"}
        </button>
      )}
    </div>
  );
  const placePreview = selectedPlace && (
    <section
      className="rental-map-preview map-place-preview"
      aria-label="Selected nearby place"
      aria-live="polite"
    >
      <button
        type="button"
        className="rental-preview-close"
        aria-label="Close place preview"
        onClick={() => setSelectedPlaceId(undefined)}
      >
        <X size={18} />
      </button>
      <h3>{selectedPlace.name}</h3>
      <p>{selectedPlace.type === "metro" ? "Metro station" : "University"}</p>
      <p>Approximate reference location.</p>
      {apiMode === "mock" && <p>Demo location</p>}
    </section>
  );
  const nearbyList = showNearby && places.length > 0 && (
    <details className="map-nearby-list">
      <summary>Nearby places ({places.length})</summary>
      <ul>
        {places.map((place) => (
          <li key={place.id}>
            <button
              type="button"
              onClick={() => {
                setSelectedPlaceId(place.id);
                setSelectedId(undefined);
              }}
            >
              {place.name} · {place.type === "metro" ? "Metro station" : "University"}
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
  const areaSearch = onSearchArea && (
    <div className="map-area-search">
      <button
        type="button"
        className="map-expand-button map-search-button"
        disabled={pending || !validArea || viewportBbox === bbox}
        onClick={() => {
          if (viewportBbox && validArea) onSearchArea(viewportBbox);
        }}
      >
        {pending ? "Searching…" : "Search this area"}
      </button>
      {bbox && onClearArea && (
        <button type="button" className="map-expand-button" onClick={onClearArea}>
          <X size={14} aria-hidden="true" /> Clear area
        </button>
      )}
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
      {!showDemoSurface && showDistrictPrices && (
        <div className="mb-2">
          <h3>District rent price guide</h3>
          <div
            className="map-price-ramp"
            style={{ background: "linear-gradient(to right, #16a34a 0%, #facc15 50%, #dc2626 100%)" }}
            aria-hidden="true"
          />
          <p>Green = lower, yellow = middle, red = higher asking rent per m².</p>
        </div>
      )}
      {showDemoSurface ? (
        <>
          <p className="map-demo-label">Demo data</p>
          <h3>Monthly asking rent / m²</h3>
          <div className="map-price-ramp" aria-hidden="true" />
          <div className="map-price-ticks">
            <span>6</span><span>12</span><span>18</span><span>24</span>
          </div>
          <p>USD / m² / month</p>
          <p><span className="map-no-data-key" /> No data</p>
        </>
      ) : !showDistrictPrices ? (
        <p className="map-demo-label">District price layer hidden</p>
      ) : (districtQuery.isPending || snapshotQuery.isPending && !weeklySupported) ? (
        <p role="status" className="map-demo-label">
          Loading available district pricing evidence…
        </p>
      ) : !priceRange || activePrices.length === 0 ? (
        <>
          <p className="map-demo-label">District shading unavailable</p>
          <p>No district has at least five usable rent-per-m² listings in the available data.</p>
          <p>Uncolored areas do not mean zero rent. Weekly data and active listing samples cannot be substituted with estimates.</p>
          {(snapshotQuery.isError || districtQuery.isError) && (
            <button type="button" className="underline" onClick={() => {
              void districtQuery.refetch();
              void snapshotQuery.refetch();
            }}>Retry prices</button>
          )}
        </>
      ) : (
        <>
          <p className="map-demo-label">{useSnapshot ? "Current active listings snapshot" : "Published weekly district index"}</p>
          <p>Median monthly asking rent per m² (USD)</p>
          <div className="map-price-ticks">
            <span>{priceRange.minimum.toFixed(2)} USD</span>
            <span>{((priceRange.minimum + priceRange.maximum) / 2).toFixed(2)} USD</span>
            <span>{priceRange.maximum.toFixed(2)} USD</span>
          </div>
          {useSnapshot ? (
            <>
              <p>Based on {snapshotQuery.data?.listings.length ?? 0} loaded active listings. {activePrices.length} districts meet the five-listing threshold.</p>
              {snapshotQuery.data?.truncated && <p>Partial sample: only the first 1,500 listing rows were analyzed.</p>}
              <p>Most recent listing observation: {snapshotSummary.latestObservation?.slice(0, 10) ?? "unknown"}. This is not a weekly historical price trend.</p>
            </>
          ) : (
            <>
              <p>Data week: {districtSummary.periodStart} to {districtSummary.periodEnd}</p>
              <p>{activePrices.length} of 12 districts have supported weekly rent-per-m² data.</p>
              {districtSummary.staleCount > 0 && <p>Warning: some source observations are stale.</p>}
              {districtSummary.latestPublishedPeriod !== districtSummary.periodStart &&
                <p>Most recent published week lacks sufficient data, so an older supported period is displayed.</p>}
            </>
          )}
          <p><span className="map-no-data-key" /> Uncolored districts lack sufficient data.</p>
          <p className="text-xs">District medians are asking rents, not street-level prices or model predictions.</p>
        </>
      )}
    </aside>
  );
  const [selectedId, setSelectedId] = useState<string>();
  const [overlappingIds, setOverlappingIds] = useState<readonly string[]>([]);
  const selectedLocation = mapLocations?.find(({ id }) => id === selectedId);
  const details = useQuery({
    queryKey: ["map-listing-detail", apiMode, selectedId],
    queryFn: ({ signal }) => getListingDetails(selectedId!, signal),
    enabled: selectedLocation !== undefined,
    retry: false,
  });
  const selectRental = useCallback((id: string) => {
    setOverlappingIds([]);
    setSelectedId(id);
    setSelectedPlaceId(undefined);
  }, []);
  const selectPlace = useCallback((id: string) => {
    setOverlappingIds([]);
    setSelectedPlaceId(id);
    setSelectedId(undefined);
  }, []);
  const selectOverlap = useCallback((ids: string[]) => {
    // Several rentals may share approximate coordinates. Preview the first one
    // immediately instead of forcing users through an anonymous numbered list.
    setSelectedId(ids[0]);
    setSelectedPlaceId(undefined);
    setOverlappingIds(ids);
  }, []);
  const points = useMemo(
    () =>
      mapLocations?.map((location) => ({
        ...location,
        label: "Show rental preview",
        approximate: location.coordinate_confidence === "approximate",
      })) ??
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
    [mapLocations, listings, format],
  );
  const selected = mapLocations
    ? selectedLocation && details.data?.listing
    : listings.find((listing) => listing.id === selectedId && hasMapCoordinates(listing));
  const markerProps = {
    viewMode,
    points: mapLocations || bbox ? points : [],
    clustered: mapLocations !== undefined,
    onOverlap: selectOverlap,
    showDemoSurface,
    places,
    districtPrices: !showDemoSurface && showDistrictPrices ? activePrices : undefined,
    priceRange: !showDemoSurface && showDistrictPrices ? priceRange : null,
    selectedPlaceId,
    onSelectPlace: selectPlace,
    selectedId,
    onSelect: selectRental,
    bbox,
  };
  const coverage = pending
    ? "Loading rental locations…"
    : failed
      ? "Rental locations unavailable."
      : mapLocations
        ? `${points.length.toLocaleString()} rentals with usable locations.`
        : !bbox
          ? "Rental results are also available in the catalogue below."
          : `${points.length} of ${listings.length} rentals on this results page have usable locations.${hasMore ? " More results are available in the catalogue." : ""}`;
  const overlappingPosition =
    selectedId === undefined ? -1 : overlappingIds.indexOf(selectedId);
  const hasOtherRentals = overlappingIds.length > 1 && overlappingPosition >= 0;
  const navigateOverlap = (direction: -1 | 1) => {
    if (!hasOtherRentals) return;
    const nextIndex =
      (overlappingPosition + direction + overlappingIds.length) % overlappingIds.length;
    setSelectedId(overlappingIds[nextIndex]);
  };
  const detailsStatus = selectedLocation && (details.isPending || details.isError) && (
    <section className="rental-map-preview" role="status">
      {details.isPending ? "Loading rental preview…" : "Rental preview unavailable."}
      {details.isError && (
        <button type="button" onClick={() => void details.refetch()}>
          Retry preview
        </button>
      )}
    </section>
  );
  const preview = (mapLocations || bbox) && selected && (
    <section className="rental-map-preview" aria-label="Selected rental" aria-live="polite">
      <button
        type="button"
        className="rental-preview-close"
        aria-label="Close rental preview"
        onClick={() => {
          setSelectedId(undefined);
          setOverlappingIds([]);
        }}
      >
        <X size={18} />
      </button>
      {hasOtherRentals && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="font-semibold">
            Rental {overlappingPosition + 1} of {overlappingIds.length} at this location
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-md border px-2 py-1"
              aria-label="Previous rental at this location"
              onClick={() => navigateOverlap(-1)}
            >
              Previous
            </button>
            <button
              type="button"
              className="rounded-md border px-2 py-1"
              aria-label="Next rental at this location"
              onClick={() => navigateOverlap(1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
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
              {viewModeControls}
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
            {!expanded && <Suspense
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
                onCameraChange={(camera) => {
                  if (!expanded) rememberCamera(camera);
                }}
                {...markerProps}
              />
            </Suspense>}
            {!expanded && gradientLegend}
            {!expanded && (placePreview || preview || detailsStatus)}
          </div>
          <p className="rental-map-coverage" role="status">
            {areaStatus} {coverage}
            {failed && onRetry && (
              <button type="button" onClick={onRetry}>
                Retry map
              </button>
            )}
          </p>

          {placeControls}
          {nearbyList}
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
                <p id={descriptionId} className="sr-only">
                  Drag to explore and use the wheel to zoom. Close or press Escape to return to your
                  search.
                </p>
              </div>
              <div className="map-toolbar-actions">
                {viewModeControls}
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
              {placePreview || preview || detailsStatus}
              <p className="rental-map-coverage rental-map-coverage-expanded" role="status">
                {areaStatus} {coverage}
                {failed && onRetry && (
                  <button type="button" onClick={onRetry}>
                    Retry map
                  </button>
                )}
              </p>
            </div>
            {placeControls}
            {nearbyList}
          </>
        )}
      </dialog>
    </section>
  );
}
