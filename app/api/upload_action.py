import requests
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.clients.shopify_client import ShopifyClient

router = APIRouter()


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """
    Uploads a local image file to Shopify via staged uploads.

    Flow:
      1. Ask Shopify for a pre-signed staging URL (stagedUploadsCreate)
      2. PUT the file bytes to that staging URL
      3. Return the resourceUrl — a permanent Shopify CDN URL
         that can be passed to productCreateMedia as originalSource
    """

    client = ShopifyClient()

    # Read file bytes
    file_bytes = await file.read()
    filename = file.filename or "upload.jpg"
    mime_type = file.content_type or "image/jpeg"
    file_size = len(file_bytes)

    # --------------------------------------------------
    # STEP 1: Request a staged upload target from Shopify
    # --------------------------------------------------
    stage_resp = client.graphql(
        """
        mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
          stagedUploadsCreate(input: $input) {
            stagedTargets {
              url
              resourceUrl
              parameters {
                name
                value
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """,
        {
            "input": [
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "resource": "IMAGE",
                    "fileSize": str(file_size),
                    "httpMethod": "PUT",
                }
            ]
        }
    )

    errors = stage_resp["stagedUploadsCreate"]["userErrors"]
    if errors:
        raise HTTPException(status_code=400, detail=f"Staged upload error: {errors}")

    targets = stage_resp["stagedUploadsCreate"]["stagedTargets"]
    if not targets:
        raise HTTPException(status_code=500, detail="No staged upload target returned")

    target = targets[0]
    upload_url = target["url"]
    resource_url = target["resourceUrl"]
    parameters = target["parameters"]  # extra headers/params Shopify may require

    # --------------------------------------------------
    # STEP 2: PUT the file to the staged URL
    # Shopify uses a plain PUT with Content-Type header.
    # Some targets return extra params — add them as headers if present.
    # --------------------------------------------------
    extra_headers = {"Content-Type": mime_type}
    for param in parameters:
        # Shopify staged upload params map directly to headers for PUT targets
        extra_headers[param["name"]] = param["value"]

    put_resp = requests.put(
        upload_url,
        data=file_bytes,
        headers=extra_headers,
        timeout=60,
    )

    if put_resp.status_code not in (200, 201, 204):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to Shopify staging: {put_resp.status_code} {put_resp.text[:200]}"
        )

    # --------------------------------------------------
    # STEP 3: Return the permanent CDN resource URL
    # This URL is passed to productCreateMedia as originalSource
    # --------------------------------------------------
    return {"url": resource_url}