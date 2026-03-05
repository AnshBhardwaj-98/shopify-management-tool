from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/product/new")
def create_product_page(request: Request):
    return templates.TemplateResponse(
        "product_editor.html",
        {
            "request": request,
            "mode": "create",
            "product_id": None
        }
    )


@router.get("/product/{product_id}")
def edit_product_page(product_id: str, request: Request):
    return templates.TemplateResponse(
        "product_editor.html",
        {
            "request": request,
            "mode": "edit",
            "product_id": product_id
        }
    )