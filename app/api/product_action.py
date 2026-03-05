from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from app.services.product_service import ProductService

router = APIRouter()

service = ProductService()


class VariantRequest(BaseModel):
    name: Optional[str] = None
    price: float = 0.0


class InventoryRequest(BaseModel):
    sku: Optional[str] = None
    quantity: int = 0
    track: bool = False


class SeoRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    handle: Optional[str] = None


class CreateProductRequest(BaseModel):
    title: str
    description: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    price: float = 0.0
    image: Optional[str] = None
    tags: List[str] = []
    status: str = "draft"
    variants: List[VariantRequest] = []
    inventory: Optional[InventoryRequest] = None
    seo: Optional[SeoRequest] = None


@router.post("/create-product")
def create_product(req: CreateProductRequest):
    return service.create_product(req)