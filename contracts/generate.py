"""Build the reviewable C01 OpenAPI document and synthetic examples (stdlib only)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
S = {}
def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}
def obj(name, fields):
    S[name] = {"type": "object", "additionalProperties": False,
               "required": list(fields), "properties": fields}
    return ref(name)
def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}
def enum(*values):
    return {"type": "string", "enum": list(values)}
def array(schema):
    return {"type": "array", "items": schema}
string = {"type": "string", "minLength": 1}
number = {"type": "number", "minimum": 0}
positive = {"type": "number", "exclusiveMinimum": 0}
integer = {"type": "integer", "minimum": 0}
uid = {"type": "string", "format": "uuid"}
timestamp = {"type": "string", "format": "date-time", "pattern": "Z$"}
date = {"type": "string", "format": "date"}
lat = {"type": "number", "minimum": -90, "maximum": 90}
lon = {"type": "number", "minimum": -180, "maximum": 180}
obj('Conversion', dict(rate_to_usd=positive, rate_date=date, rate_source=string))
features = dict(area_m2=nullable(positive), rooms=nullable({"type":"integer","minimum":1}),
    floor=nullable({"type":"integer","minimum":0}), total_floors=nullable({"type":"integer","minimum":1}),
    condition=nullable(enum('needs_renovation','good','renovated','new')))
obj('PropertyFeatures', features)
obj('Listing', dict(id=uid, source=enum('list.am'), external_id=string,
    source_url={"type":"string","format":"uri"}, property_id=nullable(uid), duplicate_group_id=nullable(uid),
    description=nullable(string), address=nullable(string), district_id=nullable(string),
    latitude=nullable(lat), longitude=nullable(lon), coordinate_confidence=enum('exact','approximate','unknown'),
    price_original=positive, currency_original=enum('USD','AMD','EUR','RUB'),
    price_monthly_normalized=nullable(positive), currency_normalized=enum('USD'),
    conversion=nullable(ref('Conversion')), utilities_included=nullable({"type":"boolean"}),
    **features, published_at=nullable(timestamp), first_seen_at=timestamp, last_seen_at=timestamp,
    status=enum('active','inactive')))
obj('Factor', dict(code=string, explanation=string, origin=enum('model','baseline','ontology'), evidence=array(string)))
obj('Estimate', dict(expected_price=nullable(positive), lower_bound=nullable(number), upper_bound=nullable(positive),
    currency=enum('USD'), unit=enum('USD/month'), price_status=enum('within_range','above_range','below_range','insufficient_data'),
    comparable_count=integer, confidence_explanation=string, factors=array(ref('Factor')),
    model_version=string, rules_version=string, data_as_of=nullable(timestamp), created_at=timestamp))
obj('RiskSignal', dict(id=uid, listing_id=uid, category=enum('price_anomaly','risk_evidence'),
    rule_id=string, rules_version=string, evidence=array(string), created_at=timestamp))
obj('ListingDetail', dict(listing=ref('Listing'), signals=array(ref('RiskSignal'))))
obj('ReviewEvent', dict(status=enum('pending','in_review','resolved'), decision=nullable(enum('dismissed','needs_follow_up','confirmed_issue')),
    reason=string, actor_id=uid, created_at=timestamp))
obj('Review', dict(id=uid, listing_id=uid, signal_ids=array(uid), status=enum('pending','in_review','resolved'),
    decision=nullable(enum('dismissed','needs_follow_up','confirmed_issue')), reason=nullable(string),
    reviewed_at=nullable(timestamp), updated_at=timestamp, version={"type":"integer","minimum":1}, history=array(ref('ReviewEvent'))))
obj('ReviewUpdate', dict(status=enum('in_review','resolved'), decision=nullable(enum('dismissed','needs_follow_up','confirmed_issue')),
    reason={"type":"string","minLength":1,"maxLength":2000,"pattern":"\\S"}, version={"type":"integer","minimum":1}))
S['ReviewUpdate']['allOf'] = [
    {'if': {'properties': {'status': {'const': 'resolved'}}},
     'then': {'properties': {'decision': {'type': 'string'}}},
     'else': {'properties': {'decision': {'type': 'null'}}}}
]
obj('MarketIndex', dict(district_id=string, period_start=date, period_end=date,
    sample_count=integer, area_sample_count=integer, median_usd_month=nullable(positive), median_usd_m2=nullable(positive),
    status=enum('available','insufficient_data'), data_as_of=nullable(timestamp), measure=enum('asking_price')))
obj('Statistics', dict(unit=enum('USD/month','USD/m2'), count=integer, mean=nullable(positive), sample_stddev=nullable(number)))
obj('Cohort', dict(radius_m={"type":"integer","minimum":100,"maximum":5000}, period_start=date, period_end=date,
    minimum_sample_size={"type":"integer","minimum":2}, selection_version=string,
    duplicate_policy=enum('latest_observation_per_duplicate_group'), inventory_policy=enum('active_at_data_as_of')))
S['ValuationRequest'] = {"type":"object","additionalProperties":False,"required":["latitude","longitude"],"properties":dict(
    latitude=lat, longitude=lon, radius_m={"type":"integer","minimum":100,"maximum":5000,"default":1000},
    window_days={"type":"integer","minimum":7,"maximum":90,"default":30},
    property=ref('PropertyFeatures'), asking_price_usd_month=positive)}
obj('ValuationResponse', dict(kind=enum('area_reference','property_valuation'), latitude=lat, longitude=lon,
    cohort=ref('Cohort'), monthly=ref('Statistics'), per_m2=ref('Statistics'), estimate=ref('Estimate')))
obj('ModelInput', dict(request=ref('ValuationRequest'), as_of=timestamp, district_id=nullable(string),
    distance_to_metro_m=nullable(number), distance_to_university_m=nullable(number), distance_to_center_m=nullable(number)))
obj('ErrorDetail', dict(field=string, message=string))
obj('Error', dict(code=enum('validation_error','not_found','unauthenticated','forbidden','conflict','outside_coverage','service_unavailable','internal_error'),
    message=string, request_id=uid, details=array(ref('ErrorDetail'))))
for name, item in [('ListingPage','Listing'),('ReviewPage','Review'),('MarketIndexPage','MarketIndex')]:
    obj(name, dict(items=array(ref(item)), page={"type":"integer","minimum":1}, page_size={"type":"integer","minimum":1,"maximum":100}, total=integer))

def param(name, schema, location='query', required=False):
    return dict(name=name, **{'in':location}, required=required, schema=schema)
pages=[param('page',{'type':'integer','minimum':1,'default':1}),param('page_size',{'type':'integer','minimum':1,'maximum':100,'default':20})]
filters=[param('district_id',string),param('price_min',number),param('price_max',number),param('rooms',{'type':'integer','minimum':1}),
    param('area_min',positive),param('area_max',positive),param('status',dict(enum('active','inactive'),default='active')),
    param('bbox',{'type':'string','pattern':r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$'})]
paths={}
def operation(path, method, result, parameters=(), request=None, protected=False):
    op=dict(operationId=method+'_'+path.replace('/api/v1/','').replace('/','_').replace('{','').replace('}',''),
        summary=f'{method.upper()} {path}',parameters=list(parameters),responses={
            '200':{'description':'Success','content':{'application/json':{'schema':ref(result)}}}})
    for code in ['422','500','503']+(['401','403'] if protected else [])+(['404'] if '{id}' in path else [])+(['409'] if method=='patch' else [])+(['400'] if request=='ValuationRequest' else []):
        op['responses'][code]={'description':{'400':'Outside Yerevan coverage','401':'Authentication required','403':'Reviewer role required','404':'Not found','409':'Version or transition conflict','422':'Invalid input','500':'Internal error','503':'Dependency unavailable'}[code],
            'content':{'application/json':{'schema':ref('Error')}}}
    if request:
        op['requestBody']={'required':True,'content':{'application/json':{'schema':ref(request)}}}
    if protected:
        op['security']=[{'reviewerBearer':[]}]
    paths.setdefault(path,{})[method]=op
operation('/api/v1/listings','get','ListingPage',pages+filters)
operation('/api/v1/listings/{id}','get','ListingDetail',[param('id',uid,'path',True)])
operation('/api/v1/listings/{id}/estimate','get','Estimate',[param('id',uid,'path',True)])
operation('/api/v1/valuations','post','ValuationResponse',request='ValuationRequest')
operation('/api/v1/market-index','get','MarketIndexPage',pages+[param('district_id',string),param('period_start',date),param('period_end',date)])
operation('/api/v1/reviews','get','ReviewPage',pages+[param('status',enum('pending','in_review','resolved')),param('listing_id',uid)],protected=True)
operation('/api/v1/reviews/{id}','patch','Review',[param('id',uid,'path',True)],'ReviewUpdate',True)
spec=dict(openapi='3.1.0',info=dict(title='FairRent shared contract',version='0.1.0',description='C01 proposal for owner review. No running API is implied. Normative semantics: docs/contract-semantics.md.'),
    servers=[{'url':'http://localhost:8000'}],paths=paths,components=dict(schemas=S,securitySchemes={'reviewerBearer':{'type':'http','scheme':'bearer','description':'Requires reviewer role; token issuer/session design belongs to C05.'}}))

U='00000000-0000-4000-8000-000000000001'
T='2026-10-17T08:00:00Z'
estimate=dict(expected_price=600,lower_bound=500,upper_bound=700,currency='USD',unit='USD/month',price_status='within_range',comparable_count=3,
    confidence_explanation='Synthetic calibrated interval for UI demonstration only.',factors=[],model_version='synthetic-baseline-v1',rules_version='synthetic-rules-v1',data_as_of=T,created_at=T)
insufficient=dict(estimate,expected_price=None,lower_bound=None,upper_bound=None,price_status='insufficient_data',comparable_count=1,confidence_explanation='Insufficient comparables; no prediction interval available.')
listing=dict(id=U,source='list.am',external_id='synthetic-001',source_url='https://example.org/synthetic-listing',property_id=None,duplicate_group_id=None,
    description='Synthetic apartment; no real listing or personal data.',address=None,district_id='kentron',latitude=40.185,longitude=44.515,
    coordinate_confidence='approximate',price_original=600,currency_original='USD',price_monthly_normalized=600,currency_normalized='USD',
    conversion=dict(rate_to_usd=1,rate_date='2026-10-17',rate_source='identity'),utilities_included=None,
    area_m2=50,rooms=2,floor=None,total_floors=None,condition=None,published_at=None,first_seen_at=T,last_seen_at=T,status='active')
cohort=dict(radius_m=1000,period_start='2026-09-18',period_end='2026-10-17',minimum_sample_size=3,selection_version='synthetic-cohort-v1',
    duplicate_policy='latest_observation_per_duplicate_group',inventory_policy='active_at_data_as_of')
valuation=dict(kind='property_valuation',latitude=40.185,longitude=44.515,cohort=cohort,
    monthly=dict(unit='USD/month',count=3,mean=600,sample_stddev=100),per_m2=dict(unit='USD/m2',count=3,mean=12,sample_stddev=2),estimate=estimate)
review=dict(id=U,listing_id=U,signal_ids=[U],status='pending',decision=None,reason=None,reviewed_at=None,updated_at=T,version=1,history=[])
def page(item):
    return dict(items=[item],page=1,page_size=20,total=1)
fixtures={}
def fixture(name,schema,value):
    fixtures[name]={'schema':schema,'value':value}
fixture('listings','ListingPage',page(listing))
fixture('listing-detail','ListingDetail',dict(listing=listing,signals=[dict(id=U,listing_id=U,category='price_anomaly',rule_id='synthetic-price-rule',rules_version='synthetic-rules-v1',evidence=['Price deviation requires review; not proof of fraud.'],created_at=T)]))
fixture('estimate','Estimate',estimate)
fixture('estimate-insufficient','Estimate',insufficient)
fixture('valuation-request','ValuationRequest',dict(latitude=40.185,longitude=44.515,property=dict(area_m2=50,rooms=2,floor=None,total_floors=None,condition=None),asking_price_usd_month=600))
fixture('valuation','ValuationResponse',valuation)
fixture('area-request','ValuationRequest',dict(latitude=40.185,longitude=44.515))
fixture('area-reference','ValuationResponse',dict(valuation,kind='area_reference',estimate=dict(insufficient,comparable_count=3,confidence_explanation='Area reference only: property characteristics were not supplied.')))
fixture('valuation-sparse','ValuationResponse',dict(valuation,kind='area_reference',monthly=dict(unit='USD/month',count=1,mean=500,sample_stddev=None),per_m2=dict(unit='USD/m2',count=0,mean=None,sample_stddev=None),estimate=insufficient))
fixture('listings-empty','ListingPage',dict(items=[],page=1,page_size=20,total=0))
fixture('market-index','MarketIndexPage',page(dict(district_id='kentron',period_start='2026-10-12',period_end='2026-10-18',sample_count=3,area_sample_count=3,median_usd_month=600,median_usd_m2=12,status='available',data_as_of=T,measure='asking_price')))
fixture('reviews','ReviewPage',page(review))
fixture('review-update','ReviewUpdate',dict(status='resolved',decision='dismissed',reason='Synthetic evidence checked.',version=1))
event=dict(status='resolved',decision='dismissed',reason='Synthetic evidence checked.',actor_id=U,created_at=T)
fixture('review-resolved','Review',dict(review,status='resolved',decision='dismissed',reason=event['reason'],reviewed_at=T,version=2,history=[event]))
for code in S['Error']['properties']['code']['enum']:
    fixture('error-'+code,'Error',dict(code=code,message='Synthetic '+code,request_id=U,details=[]))
from integration import align
align(S, paths, fixtures)
spec['info']['version'] = '0.2.0'
for operations in paths.values():
    for op in operations.values():
        op['description'] = 'Proposed contract; see docs/contract-semantics.md for units, nullability, ordering and runtime validation.'
for name,schema in [('listings','ListingPage'),('listing-detail','ListingDetail'),('estimate','Estimate'),('valuation','ValuationResponse'),('market-index','MarketIndexPage'),('reviews','ReviewPage'),('review-resolved','Review')]:
    for operations in paths.values():
        for op in operations.values():
            media=op['responses']['200']['content']['application/json']
            if media['schema']==ref(schema):
                media['example']=fixtures[name]['value']
for operations in paths.values():
    for op in operations.values():
        if 'requestBody' in op:
            media=op['requestBody']['content']['application/json']
            media['example']=fixtures['review-update' if media['schema']==ref('ReviewUpdate') else 'valuation-request']['value']
ROOT.mkdir(exist_ok=True)
for filename,value in [('openapi.json',spec),('fixtures.json',fixtures)]:
    (ROOT/filename).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
print(f'Generated {len(S)} schemas, {len(paths)} paths, {len(fixtures)} fixtures.')
