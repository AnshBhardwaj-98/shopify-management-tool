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

# Field mapping: grid column name → snapshot field path
_FIELD_MAP = {
    "Title": lambda p: p.get("title"),
    "Body (HTML)": lambda p: p.get("descriptionHtml"),
    "Vendor": lambda p: p.get("vendor"),
    "Type": lambda p: p.get("productType"),
    "Tags": lambda p: ", ".join(p.get("tags", [])),
    "Status": lambda p: p.get("status"),
    "Handle": lambda p: p.get("handle"),
    "SEO Title": lambda p: (p.get("seo") or {}).get("title"),
    "SEO Description": lambda p: (p.get("seo") or {}).get("description"),
}
_VARIANT_FIELD_MAP = {
    "Variant Price": lambda v: v.get("price"),
    "Variant Compare At Price": lambda v: v.get("compareAtPrice"),
    "Variant SKU": lambda v: v.get("sku"),
    "Variant Barcode": lambda v: v.get("barcode"),
}


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
    Expects: { "changes": [ { ...row fields... }, ... ], "force": false }
    Each row must have at minimum: Product ID, Variant ID
    """
    changes = payload.get("changes", [])
    force = payload.get("force", False)
    if not changes:
        return {"status": "ok", "updated": 0, "errors": []}

    # ── CONFLICT DETECTION (when not forcing) ──
    if not force and _grid_store.get("ready") and _grid_store.get("snapshot"):
        conflicts = _detect_conflicts(changes, _grid_store["snapshot"])
        if conflicts:
            return {"status": "conflicts", "conflicts": conflicts}

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


# ──────────────────────────────────────────────
# LIVE CHECK — poll for external changes
# ──────────────────────────────────────────────

@router.post("/grid/live-check")
def grid_live_check():
    """
    Compare live Shopify data against the snapshot stored at load time.
    Returns cell-level diffs for any fields that changed externally.
    """
    if not _grid_store.get("ready") or not _grid_store.get("snapshot"):
        return {"diffs": [], "checked": 0}

    snapshot = _grid_store["snapshot"]
    product_ids = list(snapshot.keys())

    if not product_ids:
        return {"diffs": [], "checked": 0}

    # Batch-fetch live data using the nodes query
    all_diffs = []
    BATCH = 20  # keep batches small for speed

    for i in range(0, len(product_ids), BATCH):
        batch_ids = product_ids[i:i + BATCH]
        try:
            result = _client.graphql(
                """
                query liveCheck($ids: [ID!]!) {
                  nodes(ids: $ids) {
                    ... on Product {
                      id title descriptionHtml vendor productType
                      tags status handle updatedAt
                      seo { title description }
                      variants(first: 250) {
                        edges {
                          node { id price compareAtPrice sku barcode }
                        }
                      }
                    }
                  }
                }
                """,
                {"ids": batch_ids}
            )
        except Exception:
            continue

        for node in result.get("nodes", []):
            if not node or "id" not in node:
                continue
            pid = node["id"]
            snap = snapshot.get(pid)
            if not snap:
                continue

            snap_product = snap.get("product", {})

            # Check product-level fields
            for col_name, extractor in _FIELD_MAP.items():
                snap_val = str(extractor(snap_product) or "")
                live_val = str(extractor(node) or "")
                if snap_val != live_val:
                    all_diffs.append({
                        "product_id": pid,
                        "variant_id": None,
                        "field": col_name,
                        "old_value": snap_val,
                        "new_value": live_val,
                    })

            # Check variant-level fields
            live_variants = {
                v["node"]["id"]: v["node"]
                for v in node.get("variants", {}).get("edges", [])
            }
            snap_variants = {v["id"]: v for v in snap.get("variants", [])}

            for vid, lv in live_variants.items():
                sv = snap_variants.get(vid, {})
                if not sv:
                    continue
                for col_name, extractor in _VARIANT_FIELD_MAP.items():
                    snap_val = str(extractor(sv) or "")
                    live_val = str(extractor(lv) or "")
                    if snap_val != live_val:
                        all_diffs.append({
                            "product_id": pid,
                            "variant_id": vid,
                            "field": col_name,
                            "old_value": snap_val,
                            "new_value": live_val,
                        })

            # Update snapshot inline so next poll only shows fresh changes
            snapshot[pid]["product"] = node
            snapshot[pid]["variants"] = [
                v["node"] for v in node.get("variants", {}).get("edges", [])
            ]

        time.sleep(0.15)  # gentle rate limit

    return {"diffs": all_diffs, "checked": len(product_ids)}


# ──────────────────────────────────────────────
# CONFLICT DETECTION HELPERS
# ──────────────────────────────────────────────

def _fetch_live_product(product_id: str) -> dict | None:
    """Fetch the current live state of a product from Shopify."""
    try:
        result = _client.graphql(
            """
            query getProduct($id: ID!) {
              product(id: $id) {
                id title descriptionHtml vendor productType
                tags status handle
                seo { title description }
                variants(first: 250) {
                  edges {
                    node { id price compareAtPrice sku barcode }
                  }
                }
              }
            }
            """,
            {"id": product_id}
        )
        return result.get("product")
    except Exception:
        return None


def _detect_conflicts(changes: list, snapshot: dict) -> list:
    """
    Compare changed rows against current live Shopify data.
    A conflict exists when:
      - A field the user is changing
      - Has a different live value vs. what was in the snapshot at load time
    """
    # Group changes by product
    product_map: dict = {}
    for row in changes:
        pid = row.get("Product ID")
        if not pid:
            continue
        product_map.setdefault(pid, []).append(row)

    all_conflicts = []

    for pid, rows in product_map.items():
        snap = snapshot.get(pid)
        if not snap:
            continue  # new product not in snapshot — no conflict possible

        live = _fetch_live_product(pid)
        if not live:
            continue  # can't fetch — skip conflict check

        snap_product = snap.get("product", {})
        product_conflicts = []

        # Check product-level fields
        first_row = rows[0]
        for col_name, extractor in _FIELD_MAP.items():
            if col_name not in first_row:
                continue
            snap_val = str(extractor(snap_product) or "")
            live_val = str(extractor(live) or "")
            user_val = str(first_row[col_name] or "")
            if snap_val != live_val and user_val != live_val:
                product_conflicts.append({
                    "field": col_name,
                    "your_value": user_val,
                    "snapshot_value": snap_val,
                    "live_value": live_val,
                })

        # Build variant lookup from live data
        live_variants = {
            v["node"]["id"]: v["node"]
            for v in live.get("variants", {}).get("edges", [])
        }
        # Build variant lookup from snapshot
        snap_variants = {
            v["id"]: v for v in snap.get("variants", [])
        }

        # Check variant-level fields
        for row in rows:
            vid = row.get("Variant ID")
            if not vid:
                continue
            sv = snap_variants.get(vid, {})
            lv = live_variants.get(vid, {})
            if not sv or not lv:
                continue
            for col_name, extractor in _VARIANT_FIELD_MAP.items():
                if col_name not in row:
                    continue
                snap_val = str(extractor(sv) or "")
                live_val = str(extractor(lv) or "")
                user_val = str(row[col_name] or "")
                if snap_val != live_val and user_val != live_val:
                    product_conflicts.append({
                        "field": f"{col_name} ({vid})",
                        "your_value": user_val,
                        "snapshot_value": snap_val,
                        "live_value": live_val,
                    })

        if product_conflicts:
            all_conflicts.append({
                "product_id": pid,
                "title": first_row.get("Title", pid),
                "fields": product_conflicts,
            })

    return all_conflicts