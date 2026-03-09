from fastapi import APIRouter, HTTPException
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

@router.get("/api/product/data")
def get_product(id: str):
    # ID passed as query param: /product/data?id=gid://shopify/Product/123
    return service.get_product(id)


@router.put("/api/product/update")
def update_product(id: str, req: CreateProductRequest):
    # ID passed as query param: /product/update?id=gid://shopify/Product/123
    return service.update_product(id, req)


@router.delete("/api/product/delete")
def delete_product(id: str):
    # ID passed as query param: /api/product/delete?id=gid://shopify/Product/123
    try:
        return service.delete_product(id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))