from __future__ import annotations
import math
import re
import unicodedata

GEOGRAPHY_VERSION = "yerevan-geo-v1"
EARTH_RADIUS_M = 6_371_008.8

DISTRICTS = {
    "ajapnyak": ("Ajapnyak", "Achapnyak", "Աջափնյակ"),
    "avan": ("Avan", "Ավան"),
    "arabkir": ("Arabkir", "Արաբկիր"),
    "davtashen": ("Davtashen", "Դավթաշեն"),
    "erebuni": ("Erebuni", "Էրեբունի"),
    "kentron": ("Kentron", "Կենտրոն", "Center", "Centre"),
    "malatia-sebastia": ("Malatia-Sebastia", "Malatia Sebastia", "Մալաթիա-Սեբաստիա"),
    "nor-nork": ("Nor Nork", "Nork", "Նոր Նորք"),
    "nork-marash": ("Nork-Marash", "Nork Marash", "Նորք-Մարաշ"),
    "nubarashen": ("Nubarashen", "Նուբարաշեն"),
    "shengavit": ("Shengavit", "Շենգավիթ"),
    "kanaker-zeytun": ("Kanaker-Zeytun", "Kanaker Zeytun", "Քանաքեռ-Զեյթուն"),
}


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = re.sub(r"[‐‑‒–—_]+", "-", value)
    return re.sub(r"\s+", " ", value)


_DISTRICT_IDS = {_key(alias): district_id
                 for district_id, aliases in DISTRICTS.items() for alias in aliases}


def normalize_district(value: str | None) -> str | None:
    """Normalize an explicit source field. Unknown values are never inferred."""
    return _DISTRICT_IDS.get(_key(value)) if isinstance(value, str) and value.strip() else None


# Coordinates are approximate reference points. The code version is part of every feature row.
# Metro roster is the Municipality's 10 stations; point coords are from the linked Citylines feed.
METRO_STATIONS = (
    ("barekamutyun", "Barekamutyun", 40.19696, 44.49440,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("marshal-baghramyan", "Marshal Baghramyan", 40.19150, 44.50773,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("yeritasardakan", "Yeritasardakan", 40.18592, 44.51963,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("hanrapetutyan-hraparak", "Republic Square", 40.17767, 44.51562,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("zoravar-andranik", "Zoravar Andranik", 40.17129, 44.51215,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("sasuntsi-davit", "Sasuntsi Davit", 40.15473, 44.50712,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("gortsaranayin", "Gortsaranayin", 40.14105, 44.49850,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("shengavit", "Shengavit", 40.14503, 44.48551,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("garegin-nzhdeh-hraparak", "Garegin Nzhdeh Square", 40.15019, 44.48243,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
    ("charbakh", "Charbakh", 40.14063, 44.47072,
     "https://cdn.citylines.co/api/yerevan/raw_source/stations"),
)

# Main-campus/place markers (starter coverage, not a complete university census).
UNIVERSITIES = (
    ("ysu-main", "Yerevan State University", 40.181592, 44.526469,
     "https://musicbrainz.org/place/8af9b853-bde3-4f3c-9d34-e33ba0a7f1fe/aliases"),
    ("npu-armenia-main", "National Polytechnic University of Armenia", 40.191305, 44.523147,
     "https://musicbrainz.org/place/989ee6a7-d608-4ce7-9743-b09b0970aac5/map"),
    ("ysmu-main", "Yerevan State Medical University", 40.1883981, 44.5258767,
     "https://mapy.com/en/?id=137842227&source=osm"),
    ("aua-main", "American University of Armenia", 40.19322, 44.50467,
     "https://am.geoview.info/american_university_of_armenia%2C13156191"),
)

# Center policy: Republic Square central reference point, not the full Kentron district.
CITY_CENTER = (40.17767, 44.51562, "republic-square",
               "https://cdn.citylines.co/api/yerevan/raw_source/stations")


def reference_points() -> tuple[dict, ...]:
    """Normalized point registry rows; source URLs and coordinate quality travel with every point."""
    records = [
        {"id": point[0], "name": point[1], "kind": "metro", "latitude": point[2],
         "longitude": point[3], "coordinate_source": "citylines-station-point",
         "coordinate_confidence": "approximate", "source_url": point[4],
         "geography_version": GEOGRAPHY_VERSION}
        for point in METRO_STATIONS
    ]
    records.extend(
        {"id": point[0], "name": point[1], "kind": "university", "latitude": point[2],
         "longitude": point[3], "coordinate_source": "campus-place-marker",
         "coordinate_confidence": "approximate", "source_url": point[4],
         "geography_version": GEOGRAPHY_VERSION}
        for point in UNIVERSITIES
    )
    records.append({"id": CITY_CENTER[2], "name": "Republic Square", "kind": "city_center",
                    "latitude": CITY_CENTER[0], "longitude": CITY_CENTER[1],
                    "coordinate_source": "citylines-republic-square-point",
                    "coordinate_confidence": "approximate", "source_url": CITY_CENTER[3],
                    "geography_version": GEOGRAPHY_VERSION})
    return tuple(records)


def haversine_m(latitude: float, longitude: float,
                other_latitude: float, other_longitude: float) -> float:
    """Great-circle straight-line surface distance in metres (WGS84 coordinates)."""
    phi1, phi2 = math.radians(latitude), math.radians(other_latitude)
    d_phi = phi2 - phi1
    d_lambda = math.radians(other_longitude - longitude)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def proximity_features(latitude: float | None, longitude: float | None) -> dict:
    """Create nullable nearest-infrastructure and center features for one point."""
    result = {
        "distance_metro_m": None, "nearest_metro_id": None,
        "distance_university_m": None, "nearest_university_id": None,
        "distance_center_m": None, "geography_version": GEOGRAPHY_VERSION,
        "geo_status": "unresolved",
    }
    if latitude is None or longitude is None:
        return result
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return result
    nearest_metro = min(METRO_STATIONS,
                        key=lambda p: haversine_m(latitude, longitude, p[2], p[3]))
    nearest_university = min(UNIVERSITIES,
                             key=lambda p: haversine_m(latitude, longitude, p[2], p[3]))
    result.update(
        distance_metro_m=round(haversine_m(latitude, longitude, nearest_metro[2], nearest_metro[3]), 1),
        nearest_metro_id=nearest_metro[0],
        distance_university_m=round(haversine_m(latitude, longitude,
                                                 nearest_university[2], nearest_university[3]), 1),
        nearest_university_id=nearest_university[0],
        distance_center_m=round(haversine_m(latitude, longitude, CITY_CENTER[0], CITY_CENTER[1]), 1),
        geo_status="resolved",
    )
    return result
