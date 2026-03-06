from fastapi import APIRouter
from fastapi.responses import StreamingResponse, Response
from app.services.bulk_fetch_service import BulkFetchService
from app.clients.shopify_client import ShopifyClient
import json
import time

router = APIRouter()
_service = BulkFetchService()
_client = ShopifyClient()

# In-memory store for the last loaded grid data
_grid_store: dict = {"rows": None, "snapshot": None, "ready": False}


def sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ──────────────────────────────────────────────
# LOAD — SSE stream that runs bulk fetch then
# sends all rows as a single "data" event
# ──────────────────────────────────────────────

@router.post("/grid/load")
def grid_load():
    def generate():
        yield ": keep-alive\n\n"

        try:
            yield sse({"type": "log", "msg": "🚀 Starting Shopify bulk sync..."})

            def log(msg):
                pass  # We'll flush all at once after

            logs = []

            rows, snapshot = _service.full_sync(
                progress_callback=lambda msg: logs.append(msg)
            )

            for msg in logs:
                yield sse({"type": "log", "msg": msg})

            _grid_store["rows"] = rows
            _grid_store["snapshot"] = snapshot
            _grid_store["ready"] = True

            yield sse({
                "type": "ready",
                "rows": rows,
                "count": len(rows),
            })

        except Exception as e:
            yield sse({"type": "error", "msg": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ──────────────────────────────────────────────
# SAVE — receives changed rows, pushes to Shopify
# ──────────────────────────────────────────────

@router.post("/grid/save")
def grid_save(payload: dict):
    """
    Expects: { "changes": [ { ...row fields... }, ... ] }
    Each row must have at minimum: Product ID, Variant ID
    """
    changes = payload.get("changes", [])
    if not changes:
        return {"status": "ok", "updated": 0, "errors": []}

    results = {"updated": 0, "errors": []}

    # Group changes by product for efficient variant bulk update
    product_map: dict = {}
    for row in changes:
        pid = row.get("Product ID")
        vid = row.get("Variant ID")
        if not pid or not vid:
            results["errors"].append({"row": row, "error": "Missing Product ID or Variant ID"})
            continue
        product_map.setdefault(pid, []).append(row)

    for product_id, rows in product_map.items():
        try:
            # ── 1. Product-level fields (use first row — they're the same per product) ──
            first = rows[0]
            product_input = {"id": product_id}

            if "Title" in first:
                product_input["title"] = first["Title"]
            if "Body (HTML)" in first:
                product_input["descriptionHtml"] = first["Body (HTML)"]
            if "Vendor" in first:
                product_input["vendor"] = first["Vendor"]
            if "Type" in first:
                product_input["productType"] = first["Type"]
            if "Tags" in first:
                raw = first["Tags"]
                product_input["tags"] = [t.strip() for t in raw.split(",") if t.strip()] if raw else []
            if "Status" in first:
                product_input["status"] = first["Status"].upper() if first["Status"] else "DRAFT"
            if "SEO Title" in first or "SEO Description" in first:
                product_input["seo"] = {
                    "title": first.get("SEO Title", ""),
                    "description": first.get("SEO Description", ""),
                }
            if "Handle" in first:
                product_input["handle"] = first["Handle"]

            if len(product_input) > 1:  # more than just id
                resp = _client.graphql(
                    """
                    mutation productUpdate($input: ProductInput!) {
                      productUpdate(input: $input) {
                        product { id }
                        userErrors { field message }
                      }
                    }
                    """,
                    {"input": product_input}
                )
                errs = resp["productUpdate"]["userErrors"]
                if errs:
                    raise Exception(f"Product update errors: {errs}")

            # ── 2. Variant-level fields ──
            variants_payload = []
            for row in rows:
                vid = row.get("Variant ID")
                v = {"id": vid}
                if "Variant Price" in row:
                    try:
                        v["price"] = str(float(row["Variant Price"]))
                    except:
                        pass
                if "Variant Compare At Price" in row:
                    val = row["Variant Compare At Price"]
                    v["compareAtPrice"] = str(float(val)) if val else None
                if "Variant SKU" in row:
                    v["inventoryItem"] = {"sku": row["Variant SKU"]}
                if "Variant Barcode" in row:
                    v["barcode"] = row["Variant Barcode"]
                variants_payload.append(v)

            if variants_payload:
                resp = _client.graphql(
                    """
                    mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                        productVariants { id price }
                        userErrors { field message }
                      }
                    }
                    """,
                    {"productId": product_id, "variants": variants_payload}
                )
                errs = resp["productVariantsBulkUpdate"]["userErrors"]
                if errs:
                    raise Exception(f"Variant update errors: {errs}")

            results["updated"] += len(rows)
            time.sleep(0.2)  # gentle rate limit

        except Exception as e:
            results["errors"].append({"product_id": product_id, "error": str(e)})

    results["status"] = "ok" if not results["errors"] else "partial"
    return results