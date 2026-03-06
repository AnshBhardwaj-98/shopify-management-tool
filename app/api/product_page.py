from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/product/new")
def create_product_page(request: Request):
    return templates.TemplateResponse(
        "product_editor.html",
        {
            "request": request,
            "mode": "create",
            "product_id": ""
        }
    )


@router.get("/product/{product_id:path}")
def edit_product_page(product_id: str, request: Request):
    # FastAPI with :path captures everything including slashes
    # e.g. /product/gid://shopify/Product/123 → product_id = "gid://shopify/Product/123"
    return templates.TemplateResponse(
        "product_editor.html",
        {
            "request": request,
            "mode": "edit",
            "product_id": product_id
        }
    )