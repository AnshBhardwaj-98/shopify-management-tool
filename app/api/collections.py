from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from app.services.collection_service import CollectionService

router = APIRouter()
service = CollectionService()
templates = Jinja2Templates(directory="app/templates")

class UpdateCollectionRequest(BaseModel):
    title: str
    descriptionHtml: Optional[str] = None

@router.get("/collections")
def collections_page(request: Request):
    """Renders the collections dashboard."""
    return templates.TemplateResponse("collections.html", {"request": request})

@router.get("/collections/edit")
def collection_editor_page(request: Request, id: str):
    """Renders the collection editor for a specific ID."""
    return templates.TemplateResponse("collection_editor.html", {"request": request, "collection_id": id})

@router.get("/api/collection/list")
def list_collections():
    """Returns a list of all collections for the dashboard."""
    try:
        return service.get_collections()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/collection/data")
def get_collection(id: str):
    """Returns detailed data for a single collection."""
    try:
        return service.get_collection(id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/collection/update")
def update_collection(id: str, req: UpdateCollectionRequest):
    """Updates a collection's basic details."""
    try:
        return service.update_collection(id, req.title, req.descriptionHtml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
