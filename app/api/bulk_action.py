from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.services.bulk_service import BulkService
import json
import time
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()
service = BulkService()

_abort_flag = False


def event(data: dict) -> str:
    """Format a dict as an SSE message."""
    return f"data: {json.dumps(data)}\n\n"


class BulkPriceIncreaseRequest(BaseModel):
    percentage: float
    variant_ids: Optional[List[str]] = None

@router.post("/bulk/price-increase")
def bulk_price_increase(
    percentage: float | None = Query(default=None),
    request: BulkPriceIncreaseRequest | None = Body(default=None),
):
    """
    Streams live progress via Server-Sent Events.
    Yields a keep-alive ping immediately so the browser
    does not show "Connecting..." while get_products() runs.
    """

    # Support both request styles:
    # 1) POST /bulk/price-increase?percentage=10
    # 2) POST /bulk/price-increase with JSON body
    effective_percentage = request.percentage if request else percentage
    if effective_percentage is None:
        raise HTTPException(status_code=422, detail="percentage is required")

    def generate():
        global _abort_flag
        _abort_flag = False

        target_variants = set(request.variant_ids) if request and request.variant_ids else None

        # Ping immediately so the browser sees the connection is alive
        yield ": keep-alive\n\n"

        products = service.client.get_products()
        total = len(products)

        yield event({"type": "start", "total": total})

        updated = 0
        failed = 0

        for product in products:
            product_id = product["id"]
            title = product.get("title", "Unknown")

            try:
                variants_payload = []
                for v_edge in product["variants"]["edges"]:
                    variant = v_edge["node"]
                    variant_id = variant["id"]
                    
                    if target_variants is not None and variant_id not in target_variants:
                        continue
                        
                    old_price = float(variant["price"])
                    new_price = round(old_price * (1 + effective_percentage / 100), 2)
                    variants_payload.append({
                        "id": variant_id,
                        "price": str(new_price)
                    })

                if not variants_payload:
                    yield event({
                        "type": "skip",
                        "product_id": product_id,
                        "title": title,
                    })
                    continue

                if _abort_flag:
                    yield event({
                        "type": "aborted",
                        "updated": updated,
                        "failed": failed,
                        "total": total,
                    })
                    break

                mutation = """
                mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                    productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                        productVariants { id price }
                        userErrors { field message }
                    }
                }
                """
                response = service.client.graphql(mutation, {
                    "productId": product_id,
                    "variants": variants_payload
                })

                errors = response["productVariantsBulkUpdate"]["userErrors"]

                if errors:
                    failed += 1
                    yield event({
                        "type": "fail",
                        "product_id": product_id,
                        "title": title,
                        "errors": errors,
                        "updated": updated,
                        "failed": failed,
                        "total": total,
                    })
                else:
                    updated += 1
                    # Include updated prices so the frontend table can refresh inline
                    updated_variants = response["productVariantsBulkUpdate"]["productVariants"]
                    yield event({
                        "type": "success",
                        "product_id": product_id,
                        "title": title,
                        "variants": updated_variants,
                        "variants_updated": len(variants_payload),
                        "updated": updated,
                        "failed": failed,
                        "total": total,
                    })

                time.sleep(0.3)

            except Exception as e:
                failed += 1
                yield event({
                    "type": "error",
                    "product_id": product_id,
                    "title": title,
                    "error": str(e),
                    "updated": updated,
                    "failed": failed,
                    "total": total,
                })
                time.sleep(0.5)

        yield event({
            "type": "done",
            "total": total,
            "updated": updated,
            "failed": failed,
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering if behind a proxy
        }
    )

@router.post("/bulk/price-increase/abort")
def abort_bulk_price_increase():
    global _abort_flag
    _abort_flag = True
    return {"message": "Abort requested"}
