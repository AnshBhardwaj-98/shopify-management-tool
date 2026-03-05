from fastapi import APIRouter
from app.services.bulk_service import BulkService

router = APIRouter()

service = BulkService()


@router.post("/bulk/price-increase")
def increase_price(percentage: float):
    service.bulk_price_update(percentage)
    return {"status": "completed"}