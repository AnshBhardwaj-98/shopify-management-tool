from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.services.bulk_service import BulkService
import json
import time

router = APIRouter()
service = BulkService()


def event(data: dict) -> str:
    """Format a dict as an SSE message."""
    return f"data: {json.dumps(data)}\n\n"


@router.post("/bulk/price-increase")
def bulk_price_increase(percentage: float):
    """
    Streams live progress via Server-Sent Events.
    Yields a keep-alive ping immediately so the browser
    does not show "Connecting..." while get_products() runs.
    """

    def generate():
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
                    old_price = float(variant["price"])
                    new_price = round(old_price * (1 + percentage / 100), 2)
                    variants_payload.append({
                        "id": variant["id"],
                        "price": str(new_price)
                    })

                if not variants_payload:
                    yield event({
                        "type": "skip",
                        "product_id": product_id,
                        "title": title,
                    })
                    continue

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