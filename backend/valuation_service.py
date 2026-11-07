"""C04 orchestration: versioned B03/B07 and B06 results -> C01 -> PostgreSQL audit."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import os

import pandas as pd
from ml import market_stats, ontology_rules

try:
    from .valuation_gateway import ModelUnavailable, configured_gateway
    from .valuation_models import validate_response
    from .valuation_repository import ValuationRepository
    from .valuation_coverage import Coverage, OutsideCoverage
    from .valuation_districts import DistrictRegistry
    from .geographic_features import GEOGRAPHY_VERSION, MODEL_DISTANCE_FIELDS, district_label, model_distances
except ImportError:
    from valuation_gateway import ModelUnavailable, configured_gateway
    from valuation_models import validate_response
    from valuation_repository import ValuationRepository
    from valuation_coverage import Coverage, OutsideCoverage
    from valuation_districts import DistrictRegistry
    from geographic_features import GEOGRAPHY_VERSION, MODEL_DISTANCE_FIELDS, district_label, model_distances

POLICY_VERSION = 'c11-observed-cohort-v1-b09'


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if value else None


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
            # PostGIS supplies an indexed superset. B09 selects the exact cohort
            # for both observed statistics and model inference.
            resolved = (districts.resolve_many(connection,
                [(query.latitude, query.longitude)] + [(r.latitude, r.longitude) for r in records])
                if districts else [None] * (len(records) + 1))
            subject_district = resolved[0]
            record_districts = {str(r.id): district for r, district in zip(records, resolved[1:])}
            candidates = pd.DataFrame.from_records([
                dict(listing_id=str(r.id), price_usd=r.price_monthly_normalized, area_sqm=r.area_sqm,
                     latitude=r.latitude, longitude=r.longitude, last_seen_at=r.last_seen_at,
                     status=r.status, rooms=r.rooms, dedup_group_id=r.dedup_group_id,
                     district=record_districts[str(r.id)][0] if record_districts[str(r.id)] else None)
                for r in records
            ], columns=[*market_stats.REQUIRED, 'area_sqm', 'rooms', 'dedup_group_id', 'district'])
            rules = market_stats.CohortRules(
                radius_m=query.radius_m, window_days=min(query.window_days, market_stats.MAX_WINDOW_DAYS))
            cohort, metadata = market_stats.select_cohort(
                candidates, query.latitude, query.longitude, as_of=now, rules=rules, rooms=query.rooms,
                district=subject_district[0] if subject_district else None)
            observed = market_stats.summarize(cohort)
            observed.pop('std_dev_basis')
            data_as_of = cohort['last_seen_at'].max() if not cohort.empty else None
            stale = data_as_of is None or (now - data_as_of).total_seconds() > 60 * 86400
            selected_ids = set(cohort['listing_id'])
            columns = ['listing_id','price_usd','area_sqm','latitude','longitude',
                       'district','rooms','listing_date','dedup_group_id', *MODEL_DISTANCE_FIELDS]
            frame = pd.DataFrame([dict(listing_id=str(r.id), price_usd=r.price_monthly_normalized,
                area_sqm=r.area_sqm, latitude=r.latitude, longitude=r.longitude,
                district=(record_districts[str(r.id)][1] if record_districts[str(r.id)]
                          else None) if districts else district_label(r.district_id),
                rooms=r.rooms, listing_date=r.last_seen_at,
                dedup_group_id='group:' + r.dedup_group_id if r.dedup_group_id else 'listing:' + str(r.id),
                **model_distances(r.latitude, r.longitude))
                for r in records if str(r.id) in selected_ids], columns=columns)
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
                insufficient = (stale or len(cohort) < rules.minimum_sample_size
                                or assessment['assessment_status'] == 'INSUFFICIENT_DATA_ABSTAIN')
                if insufficient:
                    assessment = dict(estimated_price_usd=None, price_per_sqm_usd=None,
                        valuation_tier='UNCERTAIN_OUTOF_SCOPE', assessment_status='INSUFFICIENT_DATA_ABSTAIN',
                        deviation_from_baseline_pct=None)
                elif area_reference:
                    assessment = {**assessment, 'assessment_status': 'COORDINATE_BASELINE_ONLY'}
                monthly_mean = observed['cluster_mean_price_usd']
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
                result = dict(request_id=request_id,
                    coordinates=dict(latitude=query.latitude, longitude=query.longitude),
                    versions=dict(model_version=prediction['versions']['model_version'],
                                  rule_engine_version=prediction['versions'].get('rule_engine_version', ontology_rules.RULE_ENGINE_VERSION)),
                    valuation_assessment=assessment,
                    observed_market_statistics=dict(**observed,
                        data_freshness_days=max(0, (now-data_as_of).days) if data_as_of else None,
                        insufficient_data=insufficient),
                    ml_prediction_interval=interval,
                    feature_attributions=[] if insufficient else prediction.get('feature_attributions', []),
                    area_reference=(prediction.get('area_reference') if prediction.get('provenance') else
                        dict(district=None, reference_area_sqm=60,
                             note='B03 configured reference area, not a fitted district median.'))
                        if area_reference else None,
                    kind=prediction.get('kind', 'area_reference' if area_reference else 'property_valuation'),
                    cohort={key: metadata[key] for key in (
                        'radius_m', 'period_start', 'period_end', 'minimum_sample_size',
                        'selection_version', 'duplicate_policy', 'inventory_policy')},
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
