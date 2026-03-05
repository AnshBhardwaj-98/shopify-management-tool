from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from app.api import bulk_action, product_action, upload_action


from app.api import products, bulk
from app.api import product_page

app = FastAPI()

templates = Jinja2Templates(directory="app/templates")

app.include_router(products.router)
# app.include_router(bulk.router)
app.include_router(product_page.router)
app.include_router(product_action.router)
app.include_router(upload_action.router)
app.include_router(bulk_action.router)




@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )