"""Apply B02 naming and frontend requirements to the C01 proposal."""
from copy import deepcopy


def align(schemas, paths, fixtures):
    def ref(name):
        return {'$ref': '#/components/schemas/' + name}

    def null(schema):
        return {'anyOf': [schema, {'type': 'null'}]}

    def enum(*values):
        return {'type': 'string', 'enum': list(values)}

    def obj(name, fields):
        schemas[name] = {'type': 'object', 'additionalProperties': False,
                         'required': list(fields), 'properties': fields}
        return ref(name)

    def optional(schema, *names):
        schema['required'] = [n for n in schema['required'] if n not in names]

    text = {'type': 'string', 'minLength': 1}
    positive = {'type': 'number', 'exclusiveMinimum': 0}
    nonnegative = {'type': 'number', 'minimum': 0}
    count = {'type': 'integer', 'minimum': 0}
    signed = {'type': 'number'}
    stamp = {'type': 'string', 'format': 'date-time', 'pattern': 'Z$'}
    lat = {'type': 'number', 'minimum': -90, 'maximum': 90}
    lon = {'type': 'number', 'minimum': -180, 'maximum': 180}
    uri = {'type': 'string', 'format': 'uri'}
    time = '2026-10-17T08:00:00Z'
    uid = '00000000-0000-4000-8000-000000000001'

    obj('Freshness', dict(data_as_of=null(stamp), generated_at=stamp,
        is_stale={'type': 'boolean'}, max_age_days={'type': 'integer', 'minimum': 1}, policy_version=text))
    freshness = dict(data_as_of=time, generated_at=time, is_stale=False,
                     max_age_days=14, policy_version='freshness-proposal-v1')
    # B02 names are shared; database identity remains independent of training features.
    features = schemas['PropertyFeatures']['properties']
    features['area_sqm'] = features.pop('area_m2')
    features['renovation'] = null(enum('cosmetic', 'designer', 'none'))
    features['building_type'] = null(enum('monolith', 'stone', 'panel'))
    features.pop('condition')
    schemas['PropertyFeatures']['required'] = []
    listing = schemas['Listing']['properties']
    listing['area_sqm'] = listing.pop('area_m2')
    listing['dedup_group_id'] = null(text)
    listing.pop('duplicate_group_id')
    listing.pop('condition')
    listing.update(renovation=features['renovation'], building_type=features['building_type'],
        thumbnail_url=null(uri), price_status=null(enum('within_range','above_range','below_range','insufficient_data')),
        freshness=ref('Freshness'))
    schemas['Listing']['required'] = list(listing)

    request = schemas['ValuationRequest']
    request['properties'].pop('property')
    request['properties'].update(deepcopy(features))
    obj('ModelInput', dict(latitude=lat, longitude=lon, **deepcopy(features), district=null(text),
        distance_metro_m=null(nonnegative), distance_center_m=null(nonnegative),
        distance_university_m=null(nonnegative), as_of=stamp,
        radius_m=request['properties']['radius_m'], window_days=request['properties']['window_days']))
    schemas['ModelInput']['required'] = ['latitude', 'longitude', 'as_of', 'radius_m', 'window_days']
    obj('Coordinates', dict(latitude=lat, longitude=lon))
    obj('Versions', dict(model_version=text, rule_engine_version=text))
    obj('AreaReference', dict(district=null(text), reference_area_sqm=null(positive), note=text))
    obj('Assessment', dict(estimated_price_usd=null(positive), price_per_sqm_usd=null(positive),
        valuation_tier=text, assessment_status=enum('VALUATION_SUCCESS','COORDINATE_BASELINE_ONLY','INSUFFICIENT_DATA_ABSTAIN'),
        deviation_from_baseline_pct=null(signed)))
    obj('ObservedMarketStatistics', dict(cluster_mean_price_usd=null(positive), observed_price_std_dev_usd=null(nonnegative),
        comparables_count=count, data_freshness_days=null(count), insufficient_data={'type':'boolean'},
        cluster_mean_price_per_sqm_usd=null(positive), observed_price_std_dev_per_sqm_usd=null(nonnegative),
        area_comparables_count=count))
    schemas['ObservedMarketStatistics']['allOf'] = []
    for count_name, mean_name, std_name in [
        ('comparables_count','cluster_mean_price_usd','observed_price_std_dev_usd'),
        ('area_comparables_count','cluster_mean_price_per_sqm_usd','observed_price_std_dev_per_sqm_usd'),
    ]:
        schemas['ObservedMarketStatistics']['allOf'].extend([
            {'if': {'properties': {count_name: {'const': 0}}},
             'then': {'properties': {mean_name: {'type':'null'}, std_name: {'type':'null'}}}},
            {'if': {'properties': {count_name: {'maximum': 1}}},
             'then': {'properties': {std_name: {'type':'null'}}}},
        ])
    obj('PredictionInterval', dict(lower_bound_usd=null(nonnegative), upper_bound_usd=null(positive),
        confidence_level=null({'type':'number','exclusiveMinimum':0,'exclusiveMaximum':1}),
        interval_width_usd=null(nonnegative), calibration_version=null(text)))
    interval_fields = list(schemas['PredictionInterval']['properties'])
    schemas['PredictionInterval']['oneOf'] = [
        {'properties': {n: {'type': 'null'} for n in interval_fields}},
        {'properties': {n: {'not': {'type': 'null'}} for n in interval_fields}},
    ]
    obj('Attribution', dict(feature=text, impact_pct=nonnegative, direction=enum('positive','negative','neutral')))
    response_fields = dict(request_id=text, coordinates=ref('Coordinates'), versions=ref('Versions'),
        valuation_assessment=ref('Assessment'), observed_market_statistics=ref('ObservedMarketStatistics'),
        ml_prediction_interval=ref('PredictionInterval'), feature_attributions={'type':'array','items':ref('Attribution')},
        area_reference=null(ref('AreaReference')), kind=enum('area_reference','property_valuation'),
        cohort=ref('Cohort'), freshness=ref('Freshness'), explanation=text,
        price_status=enum('within_range','above_range','below_range','insufficient_data'))
    obj('ValuationResponse', response_fields)
    obj('Estimate', deepcopy(response_fields))
    schemas['ValuationResponse']['allOf'] = [
        {'if': {'properties': {'valuation_assessment': {'properties': {'assessment_status': {'const':'INSUFFICIENT_DATA_ABSTAIN'}}}}},
         'then': {'properties': {'valuation_assessment': {'properties': {n:{'type':'null'} for n in ['estimated_price_usd','price_per_sqm_usd','deviation_from_baseline_pct']}},
                                'ml_prediction_interval': {'properties': {n:{'type':'null'} for n in interval_fields}},
                                'price_status': {'const':'insufficient_data'}}}}
    ]
    schemas['Estimate']['allOf'] = deepcopy(schemas['ValuationResponse']['allOf'])
    schemas['RiskSignal']['properties']['explanation'] = text
    schemas['RiskSignal']['required'].append('explanation')
    schemas['ListingDetail']['properties']['estimate'] = null(ref('Estimate'))
    schemas['ListingDetail']['required'].append('estimate')
    schemas['Review']['properties'].update(listing=ref('Listing'), signals={'type':'array','items':ref('RiskSignal')})
    schemas['Review']['required'] += ['listing','signals']
    schemas['MarketIndex']['properties']['freshness'] = ref('Freshness')
    schemas['MarketIndex']['required'].append('freshness')
    for name in ['ListingPage', 'ReviewPage', 'MarketIndexPage']:
        schemas[name]['properties']['has_more'] = {'type':'boolean'}
        schemas[name]['required'].append('has_more')
    schemas['MarketIndexPage']['properties'].update(available_from=null({'type':'string','format':'date'}), available_to=null({'type':'string','format':'date'}))
    schemas['MarketIndexPage']['required'] += ['available_from','available_to']
    obj('InfrastructurePoint', dict(id=text, name=text, type=enum('metro','university'), latitude=lat, longitude=lon))
    obj('InfrastructurePage', dict(items={'type':'array','items':ref('InfrastructurePoint')}, page={'type':'integer','minimum':1},
        page_size={'type':'integer','minimum':1,'maximum':100}, total=count, has_more={'type':'boolean'}))
    obj('ExchangeRate', dict(base_currency=enum('USD'), quote_currency=enum('AMD'), amd_per_usd=null(positive),
        source=null(text), effective_at=null(stamp), status=enum('available','stale','unavailable'),
        freshness=ref('Freshness')))

    def parameter(name, schema):
        return {'name':name,'in':'query','required':False,'schema':schema}

    paths['/api/v1/listings']['get']['parameters'].append(parameter('sort', dict(enum('newest','price_asc','price_desc','area_asc','area_desc'),default='newest')))
    paths['/api/v1/reviews']['get']['parameters'] += [parameter('rule_id',text),parameter('category',enum('price_anomaly','risk_evidence'))]
    for p in paths['/api/v1/reviews']['get']['parameters']:
        if p['name']=='status':
            p['schema']['default']='pending'
    template = deepcopy(paths['/api/v1/market-index']['get'])
    for endpoint, result in [('infrastructure','InfrastructurePage'), ('exchange-rate','ExchangeRate')]:
        op = deepcopy(template)
        op.update(operationId='get_'+endpoint.replace('-','_'), summary='GET /api/v1/'+endpoint)
        op['responses']['200']['content']['application/json']['schema'] = ref(result)
        op['parameters'] = []
        paths['/api/v1/'+endpoint] = {'get':op}
    paths['/api/v1/infrastructure']['get']['parameters'] = deepcopy(paths['/api/v1/listings']['get']['parameters'][:2]) + [deepcopy(next(p for p in paths['/api/v1/listings']['get']['parameters'] if p['name']=='bbox')), parameter('type',enum('metro','university'))]
    paths['/api/v1/infrastructure']['get']['parameters'][2]['required']=True

    def fix_listing(value):
        value['area_sqm'] = value.pop('area_m2')
        value['dedup_group_id'] = value.pop('duplicate_group_id')
        value.pop('condition')
        value.update(renovation=None, building_type=None, thumbnail_url=None,
                     price_status='within_range', freshness=deepcopy(freshness))

    # Fixtures can share object instances in the base generator.
    seen=set()
    def walk(value):
        if isinstance(value, dict):
            if id(value) in seen:
                return
            seen.add(id(value))
            if 'source_url' in value and 'area_m2' in value:
                fix_listing(value)
            if 'items' in value and 'page_size' in value:
                value['has_more']=False
            if 'rule_id' in value:
                value['explanation']='Synthetic signal for review; not a fraud verdict.'
            for child in list(value.values()):
                walk(child)
        elif isinstance(value,list):
            for child in value:
                walk(child)
    walk(fixtures)
    cohort=deepcopy(fixtures['valuation']['value']['cohort'])
    full=dict(request_id='req_synthetic_001',coordinates=dict(latitude=40.185,longitude=44.515),
        versions=dict(model_version='synthetic-baseline-v1',rule_engine_version='synthetic-rules-v1'),
        valuation_assessment=dict(estimated_price_usd=600,price_per_sqm_usd=12,valuation_tier='Fair Market Price',assessment_status='VALUATION_SUCCESS',deviation_from_baseline_pct=0),
        observed_market_statistics=dict(cluster_mean_price_usd=600,observed_price_std_dev_usd=100,comparables_count=3,data_freshness_days=0,insufficient_data=False,
            cluster_mean_price_per_sqm_usd=12,observed_price_std_dev_per_sqm_usd=2,area_comparables_count=3),
        ml_prediction_interval=dict(lower_bound_usd=520,upper_bound_usd=680,confidence_level=0.95,interval_width_usd=160,calibration_version='synthetic-validation-fixture-v1'),
        feature_attributions=[],area_reference=None,kind='property_valuation',cohort=cohort,freshness=deepcopy(freshness),
        explanation='Synthetic independently defined interval; no measured accuracy claim.',price_status='within_range')
    area=deepcopy(full)
    area.update(kind='area_reference',area_reference=dict(district='kentron',reference_area_sqm=50,note='Training-fitted reference area; not the requested apartment area.'),price_status='insufficient_data',explanation='Area reference only; property characteristics were not provided.')
    area['valuation_assessment'].update(assessment_status='COORDINATE_BASELINE_ONLY',valuation_tier='Baseline Market Estimate')
    area['ml_prediction_interval']={n:None for n in interval_fields}
    sparse=deepcopy(area)
    sparse['valuation_assessment'].update(estimated_price_usd=None,price_per_sqm_usd=None,deviation_from_baseline_pct=None,assessment_status='INSUFFICIENT_DATA_ABSTAIN',valuation_tier='UNCERTAIN_OUTOF_SCOPE')
    sparse['observed_market_statistics'].update(cluster_mean_price_usd=500,observed_price_std_dev_usd=None,comparables_count=1,insufficient_data=True,cluster_mean_price_per_sqm_usd=None,observed_price_std_dev_per_sqm_usd=None,area_comparables_count=0)
    sparse['explanation']='Only one monthly observation; property valuation unavailable.'
    def fixture(name, schema, value):
        fixtures[name]={'schema':schema,'value':deepcopy(value)}
    for name,schema,value in [('valuation','ValuationResponse',full),('estimate','Estimate',full),('area-reference','ValuationResponse',area),('valuation-sparse','ValuationResponse',sparse),('estimate-insufficient','Estimate',sparse)]:
        fixture(name,schema,value)
    fixture('valuation-request','ValuationRequest',dict(latitude=40.185,longitude=44.515,area_sqm=50,rooms=2,asking_price_usd_month=600))
    fixtures['listing-detail']['value']['estimate']=deepcopy(full)
    listing=fixtures['listings']['value']['items'][0]
    signals=fixtures['listing-detail']['value']['signals']
    for name in ['reviews','review-resolved']:
        review=fixtures[name]['value']
        if name=='reviews':
            review=review['items'][0]
        review.update(listing=deepcopy(listing),signals=deepcopy(signals))
    market=fixtures['market-index']['value']
    market.update(available_from='2026-10-12',available_to='2026-10-18')
    market['items'][0]['freshness']=deepcopy(freshness)
    fx=dict(base_currency='USD',quote_currency='AMD',amd_per_usd=400,source='synthetic-example',effective_at=time,status='available',freshness=deepcopy(freshness))
    fx['freshness'].update(max_age_days=7,policy_version='fx-proposal-v1')
    fixture('exchange-rate','ExchangeRate',fx)
    missing=deepcopy(fx)
    missing.update(amd_per_usd=None,source=None,effective_at=None,status='unavailable')
    missing['freshness'].update(data_as_of=None,is_stale=True)
    fixture('exchange-rate-unavailable','ExchangeRate',missing)
    old_rate=deepcopy(fx)
    old_rate.update(effective_at='2026-10-01T08:00:00Z',status='stale')
    old_rate['freshness'].update(data_as_of=old_rate['effective_at'],is_stale=True)
    fixture('exchange-rate-stale','ExchangeRate',old_rate)
    fixture('infrastructure','InfrastructurePage',dict(items=[dict(id='synthetic-metro-1',name='Synthetic metro',type='metro',latitude=40.185,longitude=44.515)],page=1,page_size=20,total=1,has_more=False))
    stale=deepcopy(sparse)
    stale['freshness'].update(data_as_of='2026-07-01T08:00:00Z',is_stale=True,max_age_days=60)
    stale['observed_market_statistics']['data_freshness_days']=108
    stale['explanation']='Source snapshot exceeds provisional model freshness threshold.'
    fixture('valuation-stale','ValuationResponse',stale)
    missing_listing=deepcopy(listing)
    missing_listing.update(latitude=None,longitude=None,coordinate_confidence='unknown',area_sqm=None,rooms=None,price_status=None)
    fixture('listing-missing-fields','Listing',missing_listing)
    inactive=deepcopy(listing)
    inactive['status']='inactive'
    fixture('listing-inactive','Listing',inactive)
    stale_listing=deepcopy(listing)
    stale_listing['last_seen_at']='2026-09-01T08:00:00Z'
    stale_listing['first_seen_at']=stale_listing['last_seen_at']
    stale_listing['freshness'].update(data_as_of=stale_listing['last_seen_at'],is_stale=True)
    fixture('listing-stale','Listing',stale_listing)
    fixture('reviews-empty','ReviewPage',dict(items=[],page=1,page_size=20,total=0,has_more=False))
    fixture('market-empty','MarketIndexPage',dict(items=[],page=1,page_size=20,total=0,has_more=False,available_from=None,available_to=None))
    sparse_market=deepcopy(market['items'][0])
    sparse_market.update(sample_count=1,area_sample_count=0,median_usd_month=None,median_usd_m2=None,status='insufficient_data')
    fixture('market-sparse','MarketIndex',sparse_market)
    fixture('listings-truncated','ListingPage',dict(items=[listing],page=1,page_size=1,total=3,has_more=True))
    for endpoint,scenario in [('exchange-rate','exchange-rate'),('infrastructure','infrastructure')]:
        paths['/api/v1/'+endpoint]['get']['responses']['200']['content']['application/json']['example']=fixtures[scenario]['value']
