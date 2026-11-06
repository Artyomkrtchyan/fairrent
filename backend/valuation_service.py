"""C04 orchestration: versioned B03/B07 and B06 results -> C01 -> PostgreSQL audit."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from statistics import mean, stdev
import os

import pandas as pd
from ml.baseline import haversine_distance_km
from ml import ontology_rules

try:
    from .valuation_gateway import ModelUnavailable, configured_gateway
    from .valuation_models import validate_response
    from .valuation_repository import ValuationRepository, period
    from .valuation_coverage import Coverage, OutsideCoverage
    from .valuation_districts import DistrictRegistry
    from .geographic_features import GEOGRAPHY_VERSION, MODEL_DISTANCE_FIELDS, district_label, model_distances
except ImportError:
    from valuation_gateway import ModelUnavailable, configured_gateway
    from valuation_models import validate_response
    from valuation_repository import ValuationRepository, period
    from valuation_coverage import Coverage, OutsideCoverage
    from valuation_districts import DistrictRegistry
    from geographic_features import GEOGRAPHY_VERSION, MODEL_DISTANCE_FIELDS, district_label, model_distances

POLICY_VERSION = 'c04-observed-cohort-v4-b07'


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if value else None


def summary(values):
    return (mean(values) if values else None, stdev(values) if len(values) > 1 else None)


class ValuationService:
    def __init__(self, repository=None, provider=configured_gateway, coverage=None, clock=None):
        self.repository = repository or ValuationRepository()
        self.provider = provider
        self.coverage = coverage  # Load configuration at request time, not import/startup.
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def assess(self, query, request_id, *, subject=None, connection=None, persist=True):
        now = self.clock()
        coverage = self.coverage or Coverage()
        district_path = os.environ.get('VALUATION_DISTRICTS_FILE')
        districts = DistrictRegistry(district_path) if district_path else None
        shared_connection = connection is not None
        with (nullcontext(connection) if shared_connection else self.repository.connection()) as connection:
            if not shared_connection:
                mode = '' if persist else ' READ ONLY'
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ' + mode)
            connection.execute("SET LOCAL statement_timeout = '5s'")
            coverage.check(connection, query)
            records, dataset_version = self.repository.candidates(connection, query, now)
            if subject is not None:
                # Internal worker input, never a public request field. Exclude the subject
                # and its entire authoritative duplicate group before cohort selection.
                records = [r for r in records if r.id != subject.id and
                           (not subject.dedup_group_id or r.dedup_group_id != subject.dedup_group_id)]
            # Source grouping is authoritative. Without grouping, each listing counts once.
            # PostGIS supplies an indexed superset; use B03's exact spherical
            # distance for both public statistics and the prediction cohort.
            records = [r for r in records if haversine_distance_km(
                query.latitude, query.longitude, r.latitude, r.longitude) * 1000 <= query.radius_m]
            resolved = (districts.resolve_many(connection,
                [(query.latitude, query.longitude)] + [(r.latitude, r.longitude) for r in records])
                if districts else [None] * (len(records) + 1))
            subject_district = resolved[0]
            record_districts = {str(r.id): district for r, district in zip(records, resolved[1:])}
            ordered = sorted(records, key=lambda r: (-r.last_seen_at.timestamp(), str(r.id)))
            groups, selected = set(), []
            for record in ordered:
                key = 'group:' + record.dedup_group_id if record.dedup_group_id else 'listing:' + str(record.id)
                if key not in groups:
                    groups.add(key)
                    selected.append((record, key))
            # Exact rooms, no silent widening. Unknown area still contributes to monthly statistics.
            selected = [(r, key) for r, key in selected if query.rooms is None or r.rooms == query.rooms]
            if subject_district:
                selected = [(r, key) for r, key in selected
                            if record_districts[str(r.id)] == subject_district]
            data_as_of = max((r.last_seen_at for r, _ in selected), default=None)
            stale = data_as_of is None or (now - data_as_of).total_seconds() > 60 * 86400
            columns = ['listing_id','price_usd','area_sqm','latitude','longitude',
                       'district','rooms','listing_date','dedup_group_id', *MODEL_DISTANCE_FIELDS]
            frame = pd.DataFrame([dict(listing_id=str(r.id), price_usd=r.price_monthly_normalized,
                area_sqm=r.area_sqm, latitude=r.latitude, longitude=r.longitude,
                district=(record_districts[str(r.id)][1] if record_districts[str(r.id)]
                          else None) if districts else district_label(r.district_id),
                rooms=r.rooms, listing_date=r.last_seen_at,
                dedup_group_id=key, **model_distances(r.latitude, r.longitude))
                for r, key in selected], columns=columns)
            payload = query.model_dump(exclude={'asking_price_usd_month', 'radius_m', 'window_days'})
            payload.update(model_distances(query.latitude, query.longitude))
            if districts:
                payload['district'] = subject_district[1] if subject_district else None
            area_reference = query.area_sqm is None or query.rooms is None
            if area_reference:
                payload['area_sqm'] = None
            try:
                prediction = self.provider(frame, dataset_version=dataset_version).assess(
                    payload, as_of=now, radius_m=query.radius_m, window_days=query.window_days)
                assessment = prediction['valuation_assessment']
                insufficient = stale or assessment['assessment_status'] == 'INSUFFICIENT_DATA_ABSTAIN'
                if insufficient:
                    assessment = dict(estimated_price_usd=None, price_per_sqm_usd=None,
                        valuation_tier='UNCERTAIN_OUTOF_SCOPE', assessment_status='INSUFFICIENT_DATA_ABSTAIN',
                        deviation_from_baseline_pct=None)
                elif area_reference:
                    assessment = {**assessment, 'assessment_status': 'COORDINATE_BASELINE_ONLY'}
                prices = [r.price_monthly_normalized for r, _ in selected]
                units = [r.price_monthly_normalized / r.area_sqm for r, _ in selected if r.area_sqm is not None and r.area_sqm > 0]
                monthly_mean, monthly_std = summary(prices)
                unit_mean, unit_std = summary(units)
                if not insufficient:
                    estimate = assessment['estimated_price_usd']
                    assessment['deviation_from_baseline_pct'] = (
                        round((estimate / monthly_mean - 1) * 100, 2) if monthly_mean else None)
                ontology = prediction.get('ontology') or ontology_rules.explain_valuation(
                    payload, learned_attributions=prediction.get('feature_attributions', []))
                inference_provenance = dict(prediction.get('provenance') or {})
                inference_provenance['model_version'] = prediction['versions']['model_version']
                inference_provenance['rules_version'] = ontology_rules.RULES_VERSION
                inference_provenance['ontology'] = ontology
                inference_provenance['observed_dataset_version'] = dataset_version
                if subject is not None:
                    inference_provenance['subject_listing_id'] = str(subject.id)
                    inference_provenance['excluded_duplicate_group'] = subject.dedup_group_id
                interval = prediction.get('ml_prediction_interval')
                if insufficient or area_reference or interval is None:
                    interval = dict(lower_bound_usd=None, upper_bound_usd=None, confidence_level=None,
                                    interval_width_usd=None, calibration_version=None)
                price_status = 'insufficient_data'
                if interval['lower_bound_usd'] is not None and query.asking_price_usd_month is not None:
                    price_status = ('below_range' if query.asking_price_usd_month < interval['lower_bound_usd']
                        else 'above_range' if query.asking_price_usd_month > interval['upper_bound_usd'] else 'within_range')
                start, end, _ = period(now, query.window_days)
                start = max(start, (now - timedelta(days=60)).astimezone(ZoneInfo('Asia/Yerevan')).date())
                result = dict(request_id=request_id,
                    coordinates=dict(latitude=query.latitude, longitude=query.longitude),
                    versions=dict(model_version=prediction['versions']['model_version'],
                                  rule_engine_version=prediction['versions'].get('rule_engine_version', ontology_rules.RULE_ENGINE_VERSION)),
                    valuation_assessment=assessment,
                    observed_market_statistics=dict(cluster_mean_price_usd=monthly_mean,
                        observed_price_std_dev_usd=monthly_std, comparables_count=len(prices),
                        data_freshness_days=max(0, (now-data_as_of).days) if data_as_of else None,
                        insufficient_data=insufficient, cluster_mean_price_per_sqm_usd=unit_mean,
                        observed_price_std_dev_per_sqm_usd=unit_std, area_comparables_count=len(units)),
                    ml_prediction_interval=interval,
                    feature_attributions=[] if insufficient else prediction.get('feature_attributions', []),
                    area_reference=(prediction.get('area_reference') if prediction.get('provenance') else
                        dict(district=None, reference_area_sqm=60,
                             note='B03 configured reference area, not a fitted district median.'))
                        if area_reference else None,
                    kind=prediction.get('kind', 'area_reference' if area_reference else 'property_valuation'),
                    cohort=dict(radius_m=query.radius_m, period_start=str(start), period_end=str(end),
                        minimum_sample_size=3, selection_version=POLICY_VERSION,
                        duplicate_policy='latest_observation_per_duplicate_group', inventory_policy='active_at_data_as_of'),
                    freshness=dict(data_as_of=timestamp(data_as_of), generated_at=timestamp(now),
                        is_stale=stale, max_age_days=60, policy_version=POLICY_VERSION),
                    explanation=prediction['selection_explanation'] +
                        ' Comparable inventory uses last_seen_at as the observation date, not publication/training data. '
                        'Comparable age is capped at 60 days even if a longer window was requested. '
                        + ((f'District {subject_district[1]} ({subject_district[0]}) resolved from municipal polygons; '
                            'comparables are restricted to this district. ' if subject_district else
                            'District unresolved (polygon gap or shared boundary); radius-only cohort. ')
                           if districts else 'District polygons are not configured; radius-only cohort. ')
                        +
                        (ontology['text'] if not prediction.get('ontology') else ''),
                    price_status=price_status)
                validate_response(result)
                bounds = result['ml_prediction_interval']
                if bounds['lower_bound_usd'] is not None:
                    expected = assessment['estimated_price_usd']
                    if not (bounds['lower_bound_usd'] <= expected <= bounds['upper_bound_usd']) or abs(
                        bounds['interval_width_usd'] - (bounds['upper_bound_usd']-bounds['lower_bound_usd'])) > 0.01:
                        raise ValueError('Invalid calibrated interval')
            except (ModelUnavailable, OutsideCoverage):
                raise
            except Exception as exc:
                raise ModelUnavailable('Invalid model result') from exc
            geography_version = (coverage.version + (';districts=' + districts.version if districts else '')
                                 + ';a05=' + GEOGRAPHY_VERSION)
            if persist:
                self.repository.save(connection, query, result, dataset_version, geography_version,
                                     inference_provenance=inference_provenance)
        return result
