from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from app.services.inventory_service import InventoryService

router = APIRouter()
service = InventoryService()
templates = Jinja2Templates(directory="app/templates")


class AdjustInventoryRequest(BaseModel):
    inventoryItemId: str
    locationId: str
    availableDelta: int
    currentQuantity: int = 0  # passed from frontend to avoid extra query


@router.get("/inventory")
def inventory_page(request: Request):
    return templates.TemplateResponse("inventory.html", {"request": request})


@router.get("/api/inventory/list")
def list_inventory():
    try:
        return service.get_inventory_levels()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/inventory/adjust")
def adjust_inventory(req: AdjustInventoryRequest):
    try:
        return service.adjust_inventory(
            req.inventoryItemId,
            req.locationId,
            req.availableDelta,
            req.currentQuantity,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))