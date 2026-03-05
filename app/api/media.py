from fastapi import APIRouter, UploadFile, File
from app.services.shopify_client import ShopifyClient

router = APIRouter()
client = ShopifyClient()

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):

    content = await file.read()

    url = client.upload_image(content)

    return {"url": url}