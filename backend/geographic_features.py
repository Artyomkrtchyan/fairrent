"""C04's model-facing selection of the accepted A05 geographic features."""
from data_pipeline.geography import DISTRICTS, GEOGRAPHY_VERSION, normalize_district as normalize_a05_district, proximity_features

MODEL_DISTANCE_FIELDS = ('distance_metro_m', 'distance_university_m', 'distance_center_m')


def normalize_district(value):
    # A05 accepts source labels; internal API records can already contain a slug.
    if isinstance(value, str) and value.strip().casefold() in DISTRICTS:
        return value.strip().casefold()
    return normalize_a05_district(value)


def model_distances(latitude, longitude):
    features = proximity_features(latitude, longitude)
    return {key: features[key] for key in MODEL_DISTANCE_FIELDS}


def district_label(district_id):
    aliases = DISTRICTS.get(district_id)
    return aliases[0] if aliases else None
