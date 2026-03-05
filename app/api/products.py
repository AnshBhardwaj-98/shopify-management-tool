from fastapi import APIRouter
from app.services.product_service import ProductService

router = APIRouter()

service = ProductService()


@router.get("/products")
def get_products():
    return service.get_products()