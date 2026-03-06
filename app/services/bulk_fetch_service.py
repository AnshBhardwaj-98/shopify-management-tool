import time
import os
import io
import requests
import pandas as pd
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

try:
    import orjson as json
except Exception:
    import json

from app.clients.shopify_client import ShopifyClient

SNAPSHOT_DIR = "snapshots"
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


class BulkFetchService:

    def __init__(self):
        self.client = ShopifyClient()

    # =========================================================
    # FULL SYNC
    # =========================================================

    def full_sync(self, progress_callback=None):

        def log(msg):
            if progress_callback:
                progress_callback(msg)
            print(msg)

        log("Starting Shopify bulk operation...")
        self._start_bulk_operation()

        log("Waiting for bulk operation to complete...")
        op = self._wait_for_bulk_operation()

        log("Downloading JSONL...")
        file_path = self._download_jsonl(op["url"], "products_bulk.jsonl")

        rows, snapshot = self._parse_jsonl(file_path)
        log(f"Parsed {len(snapshot)} products, {len(rows)} variants.")

        log("Fetching locations...")
        locations = self._fetch_locations()

        inventory_ids = list(set(filter(None, (r["Inventory Item ID"] for r in rows))))

        log(f"Inventory items: {len(inventory_ids)}")

        with ThreadPoolExecutor(max_workers=2) as executor:
            inventory_future = executor.submit(
                self._fetch_inventory_levels, inventory_ids, locations
            )
            collections_future = executor.submit(self._fetch_collections)

        inventory_levels = inventory_future.result()
        product_collections = collections_future.result()

        log("Applying inventory levels...")

        for row in rows:
            inv_id = row.get("Inventory Item ID")
            if inv_id and inv_id in inventory_levels:
                for loc_name, qty in inventory_levels[inv_id].items():
                    row[f"Inventory Qty - {loc_name}"] = qty

        log("Applying collections...")

        for row in rows:
            pid = row["Product ID"]
            if pid in product_collections:
                row["Collection Names"] = ", ".join(product_collections[pid]["names"])
                row["Collection Handles"] = ", ".join(product_collections[pid]["handles"])
            else:
                row["Collection Names"] = ""
                row["Collection Handles"] = ""

        log("Sync complete.")

        return rows, snapshot

    # =========================================================
    # EXPORT
    # =========================================================

    def export_to_excel(self, progress_callback=None) -> bytes:

        rows, _ = self.full_sync(progress_callback=progress_callback)

        df = pd.DataFrame(rows)

        priority = [
            "Product ID", "Handle", "Title", "Body (HTML)", "Vendor", "Type",
            "Product Category Full Path", "Tags", "Status",
            "SEO Title", "SEO Description",
            "Variant ID", "Variant SKU", "Variant Price", "Variant Compare At Price",
            "Variant Barcode", "Variant Inventory Policy",
            "Cost per item", "Variant Grams", "Variant Weight Unit",
            "Image URLs", "Image Alt Text",
            "Collection Names", "Collection Handles",
            "Created At", "Updated At", "Last Synced",
        ]

        existing_priority = [c for c in priority if c in df.columns]
        remaining = [c for c in df.columns if c not in existing_priority]

        df = df[existing_priority + remaining]

        buf = io.BytesIO()

        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:

            df.to_excel(writer, index=False, sheet_name="Products")

            ws = writer.sheets["Products"]

            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col))
                ws.set_column(i, i, min(max_len + 2, 60))

        return buf.getvalue()

    # =========================================================
    # BULK OPERATION
    # =========================================================

    def _start_bulk_operation(self):

        bulk_query = """
        {
          products {
            edges {
              node {
                id
                handle
                title
                descriptionHtml
                vendor
                productType
                tags
                status
                createdAt
                updatedAt
                seo { title description }

                media(first:50){
                  edges{
                    node{
                      ... on MediaImage{
                        id
                        image{url altText}
                      }
                    }
                  }
                }

                variants(first:250){
                  edges{
                    node{
                      id
                      sku
                      price
                      compareAtPrice
                      barcode
                      inventoryPolicy
                      inventoryItem{
                        id
                        tracked
                        requiresShipping
                        unitCost{amount}
                        measurement{
                          weight{value unit}
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        mutation = """
        mutation bulkOperationRunQuery($query: String!) {
          bulkOperationRunQuery(query: $query) {
            bulkOperation { id status }
            userErrors { field message }
          }
        }
        """

        result = self.client.graphql(mutation, {"query": bulk_query})

        errors = result["bulkOperationRunQuery"]["userErrors"]

        if errors:
            raise Exception(errors)

    def _wait_for_bulk_operation(self, timeout=600, interval=3):

        query = """
        {
          currentBulkOperation {
            id
            status
            url
            errorCode
          }
        }
        """

        elapsed = 0

        while elapsed < timeout:

            result = self.client.graphql(query)

            op = result.get("currentBulkOperation")

            if not op:
                raise Exception("No bulk operation")

            if op["status"] == "COMPLETED":
                return op

            if op["status"] in ("FAILED", "CANCELED"):
                raise Exception(op["errorCode"])

            time.sleep(interval)
            elapsed += interval

        raise Exception("Bulk timeout")

    # =========================================================
    # STREAM DOWNLOAD
    # =========================================================

    def _download_jsonl(self, url, filename):

        path = os.path.join(SNAPSHOT_DIR, filename)

        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()

            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)

        return path

    # =========================================================
    # PARSE JSONL
    # =========================================================

    def _parse_jsonl(self, path):

        rows = []
        snapshot = {}

        products = {}
        variants = []
        product_images = {}

        with open(path, "rb") as f:

            for line in f:

                if not line.strip():
                    continue

                obj = json.loads(line)

                obj_id = obj.get("id", "")

                if obj_id.startswith("gid://shopify/Product/"):
                    products[obj_id] = obj
                    snapshot[obj_id] = {"product": obj, "variants": [], "images": []}

                elif obj_id.startswith("gid://shopify/ProductVariant/"):
                    variants.append(obj)

                elif obj_id.startswith("gid://shopify/MediaImage/"):

                    parent = obj.get("__parentId")

                    img = obj.get("image", {})

                    if parent and img.get("url"):
                        product_images.setdefault(parent, []).append(img)

        for pid in snapshot:
            snapshot[pid]["images"] = product_images.get(pid, [])

        for v in variants:
            parent = v.get("__parentId")
            if parent in snapshot:
                snapshot[parent]["variants"].append(v)

        now = datetime.now(timezone.utc).isoformat()

        for pid, data in snapshot.items():

            product = data["product"]

            images = data["images"]

            image_urls = ", ".join(img["url"] for img in images)

            for variant in data["variants"]:

                inventory = variant.get("inventoryItem") or {}

                row = {
                    "Product ID": pid,
                    "Handle": product.get("handle"),
                    "Title": product.get("title"),
                    "Vendor": product.get("vendor"),
                    "Type": product.get("productType"),
                    "Tags": ", ".join(product.get("tags", [])),
                    "Status": product.get("status"),
                    "Created At": product.get("createdAt"),
                    "Updated At": product.get("updatedAt"),
                    "SEO Title": product.get("seo", {}).get("title"),
                    "SEO Description": product.get("seo", {}).get("description"),
                    "Image URLs": image_urls,
                    "Variant ID": variant.get("id"),
                    "Variant SKU": variant.get("sku"),
                    "Variant Price": variant.get("price"),
                    "Variant Compare At Price": variant.get("compareAtPrice"),
                    "Variant Barcode": variant.get("barcode"),
                    "Variant Inventory Policy": variant.get("inventoryPolicy"),
                    "Inventory Item ID": inventory.get("id"),
                    "Inventory Tracked": inventory.get("tracked"),
                    "Requires Shipping": inventory.get("requiresShipping"),
                    "Cost per item": (inventory.get("unitCost") or {}).get("amount"),
                    "Last Synced": now,
                }

                rows.append(row)

        return rows, snapshot

    # =========================================================
    # LOCATIONS
    # =========================================================

    def _fetch_locations(self):

        result = self.client.graphql("""
        {
          locations(first:50){
            edges{
              node{id name}
            }
          }
        }
        """)

        return {
            e["node"]["id"]: e["node"]["name"]
            for e in result["locations"]["edges"]
        }

    # =========================================================
    # FAST INVENTORY BATCH FETCH
    # =========================================================

    def _fetch_inventory_levels(self, inventory_item_ids, locations):

        query = """
        query($ids:[ID!]!){
          nodes(ids:$ids){
            ... on InventoryItem{
              id
              inventoryLevels(first:20){
                edges{
                  node{
                    location{id}
                    quantities(names:["available"]){
                      quantity
                    }
                  }
                }
              }
            }
          }
        }
        """

        inventory_data = {}

        BATCH = 50

        for i in range(0, len(inventory_item_ids), BATCH):

            batch = inventory_item_ids[i:i+BATCH]

            result = self.client.graphql(query, {"ids": batch})

            for node in result["nodes"]:

                if not node:
                    continue

                inv_id = node["id"]

                data = {}

                for level in node["inventoryLevels"]["edges"]:

                    loc = level["node"]["location"]["id"]

                    qty = level["node"]["quantities"][0]["quantity"]

                    name = locations.get(loc)

                    if name:
                        data[name] = qty

                inventory_data[inv_id] = data

        return inventory_data

    # =========================================================
    # COLLECTIONS
    # =========================================================

    def _fetch_collections(self):

        result = self.client.graphql("""
        {
          collections(first:250){
            edges{
              node{
                id
                title
                handle
                products(first:250){
                  edges{
                    node{id}
                  }
                }
              }
            }
          }
        }
        """)

        product_collections = {}

        for edge in result["collections"]["edges"]:

            col = edge["node"]

            for p in col["products"]["edges"]:

                pid = p["node"]["id"]

                product_collections.setdefault(pid, {"names": [], "handles": []})

                product_collections[pid]["names"].append(col["title"])
                product_collections[pid]["handles"].append(col["handle"])

        return product_collections