from fastapi import APIRouter, Depends, HTTPException, Request

try:
    from .valuation_models import ValuationRequest
    from .valuation_service import ValuationService
except ImportError:
    from valuation_models import ValuationRequest
    from valuation_service import ValuationService

router = APIRouter(prefix='/api/v1/valuations', tags=['valuations'])


def service():
    return ValuationService()


@router.post('')
def valuation(body: ValuationRequest, request: Request, evaluator=Depends(service)):
    if request.query_params:
        raise HTTPException(422, 'This endpoint accepts no query parameters')
    return evaluator.assess(body, request.state.request_id)
