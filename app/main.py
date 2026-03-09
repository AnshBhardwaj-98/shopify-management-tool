from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.api import product_action, products, product_page
from app.api import upload_action
from app.api import bulk_action
from app.api import export_action
from app.api import grid_action
from app.api import collections
from app.api import inventory

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

app.include_router(products.router)
app.include_router(product_action.router)  # ← must be before product_page (catch-all)
app.include_router(upload_action.router)
app.include_router(bulk_action.router)
app.include_router(export_action.router)
app.include_router(grid_action.router)
app.include_router(collections.router)
app.include_router(inventory.router)
app.include_router(product_page.router)   # ← catch-all HTML routes last


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )