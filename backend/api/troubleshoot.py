from fastapi import APIRouter
from backend.schemas.troubleshoot import TroubleshootRequest, TroubleshootResponse
from backend.services.orchestrator import troubleshoot

router = APIRouter()

@router.post(
    "/troubleshoot",
    response_model=TroubleshootResponse
)

def troubleshoot_device(request: TroubleshootRequest):
    return troubleshoot(request.query)






