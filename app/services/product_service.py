from app.clients.shopify_client import ShopifyClient


class ProductService:

    def __init__(self):
        self.client = ShopifyClient()
        self.location_id = "gid://shopify/Location/YOUR_LOCATION_ID"  # ← Your real location ID

    # ==================== GET PRODUCTS ====================

    def get_products(self):
        products = self.client.get_products()
        return [
            {
                "id": p["id"],
                "title": p["title"],
                "vendor": p["vendor"],
                "product_type": p["productType"],
                "image": p["featuredImage"]["url"] if p["featuredImage"] else None,
                "variants": [
                    {"id": v["node"]["id"], "price": v["node"]["price"]}
                    for v in p["variants"]["edges"]
                ],
            }
            for p in products
        ]

    # ==================== CREATE PRODUCT ====================

    def create_product(self, data):

        # -------------------------
        # 1. CREATE BASE PRODUCT
        # -------------------------
        response = self.client.graphql(
            """
            mutation productCreate($input: ProductInput!) {
              productCreate(input: $input) {
                product { id }
                userErrors { field message }
              }
            }
            """,
            {
                "input": {
                    "title": data.title,
                    "descriptionHtml": data.description or "",
                    "vendor": data.vendor,
                    "productType": data.product_type,
                    "tags": data.tags or [],
                    "status": (data.status or "draft").upper(),
                    **({"handle": data.seo.handle} if data.seo and data.seo.handle else {}),
                }
            }
        )
        errors = response["productCreate"]["userErrors"]
        if errors:
            raise Exception(f"Product creation errors: {errors}")

        product_id = response["productCreate"]["product"]["id"]

        # -------------------------
        # 2. VARIANTS
        # Shopify auto-creates a "Default Title" variant — we MUST reuse it,
        # never try to create it again.
        # -------------------------
        default_variant = self._get_default_variant(product_id)
        variants_input = data.variants or []
        real_variants = [
            v for v in variants_input
            if v.name and v.name.strip().lower() != "default title"
        ]

        if real_variants:
            # Repurpose auto-created variant as the first real variant
            self._bulk_update_variants(product_id, [{
                "id": default_variant["id"],
                "price": str(real_variants[0].price),
                "optionValues": [{"name": real_variants[0].name, "optionName": "Title"}]
            }])
            # Create remaining variants
            if len(real_variants) > 1:
                bulk_resp = self.client.graphql(
                    """
                    mutation productVariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                      productVariantsBulkCreate(productId: $productId, variants: $variants) {
                        productVariants { id price inventoryItem { id } }
                        userErrors { field message }
                      }
                    }
                    """,
                    {
                        "productId": product_id,
                        "variants": [
                            {
                                "price": str(v.price),
                                "optionValues": [{"name": v.name, "optionName": "Title"}]
                            }
                            for v in real_variants[1:]
                        ]
                    }
                )
                errs = bulk_resp["productVariantsBulkCreate"]["userErrors"]
                if errs:
                    raise Exception(f"Variant creation errors: {errs}")
        else:
            # No named variants — update price and SKU on the auto-created default variant
            update_payload = {
                "id": default_variant["id"],
                "price": f"{data.price:.2f}" if data.price else "0.00",
            }
            # Set SKU on the inventory item if provided
            if data.inventory and data.inventory.sku:
                update_payload["inventoryItem"] = {"sku": data.inventory.sku}
            self._bulk_update_variants(product_id, [update_payload])

        # Always re-fetch variants so inventoryItem.id is fresh
        variants = self._get_all_variants(product_id)

        # -------------------------
        # 3. IMAGE — non-fatal, product still succeeds if this fails
        # -------------------------
        warnings = []
        if data.image and data.image.startswith("https://"):
            try:
                self.add_product_image(product_id, data.image)
            except Exception as e:
                warnings.append(f"Image upload skipped: {e}")

        # -------------------------
        # 4. INVENTORY — non-fatal
        # Step A: enable tracking on the inventory item
        # Step B: set on-hand quantity
        # -------------------------
        if data.inventory and data.inventory.track:
            try:
                if not variants:
                    raise Exception("No variants found.")

                quantity = data.inventory.quantity or 0

                for variant in variants:
                    inv_item_id = variant["inventoryItem"]["id"]

                    # STEP A: Enable tracking
                    track_resp = self.client.graphql(
                        """
                        mutation inventoryItemUpdate($id: ID!, $input: InventoryItemInput!) {
                          inventoryItemUpdate(id: $id, input: $input) {
                            inventoryItem { id tracked }
                            userErrors { field message }
                          }
                        }
                        """,
                        {"id": inv_item_id, "input": {"tracked": True}}
                    )
                    track_errs = track_resp["inventoryItemUpdate"]["userErrors"]
                    if track_errs:
                        raise Exception(f"Tracking enable error: {track_errs}")

                    # STEP B: Set quantity
                    if quantity > 0:
                        qty_resp = self.client.graphql(
                            """
                            mutation inventorySetOnHandQuantities($input: InventorySetOnHandQuantitiesInput!) {
                              inventorySetOnHandQuantities(input: $input) {
                                inventoryAdjustments { inventoryItem { id } }
                                userErrors { field message }
                              }
                            }
                            """,
                            {
                                "input": {
                                    "reason": "correction",
                                    "setQuantities": [
                                        {
                                            "inventoryItemId": inv_item_id,
                                            "locationId": self.location_id,
                                            "quantity": quantity
                                        }
                                    ]
                                }
                            }
                        )
                        qty_errs = qty_resp["inventorySetOnHandQuantities"]["userErrors"]
                        if qty_errs:
                            raise Exception(f"Quantity error: {qty_errs}")

            except Exception as e:
                warnings.append(f"Inventory not set: {e}")

        # -------------------------
        # 5. SEO — non-fatal
        # -------------------------
        if data.seo and (data.seo.title or data.seo.description):
            try:
                self.client.graphql(
                    """
                    mutation productUpdate($input: ProductInput!) {
                      productUpdate(input: $input) {
                        product { id }
                        userErrors { field message }
                      }
                    }
                    """,
                    {
                        "input": {
                            "id": product_id,
                            "seo": {
                                "title": data.seo.title,
                                "description": data.seo.description
                            }
                        }
                    }
                )
            except Exception as e:
                warnings.append(f"SEO not set: {e}")

        return {
            "status": "success",
            "product_id": product_id,
            **({"warnings": warnings} if warnings else {})
        }

    # ==================== PRIVATE HELPERS ====================

    def _get_default_variant(self, product_id):
        result = self.client.graphql(
            """
            query($id: ID!) {
              product(id: $id) {
                variants(first: 1) {
                  edges { node { id price inventoryItem { id } } }
                }
              }
            }
            """,
            {"id": product_id}
        )
        return result["product"]["variants"]["edges"][0]["node"]

    def _get_all_variants(self, product_id):
        result = self.client.graphql(
            """
            query($id: ID!) {
              product(id: $id) {
                variants(first: 100) {
                  edges { node { id price inventoryItem { id } } }
                }
              }
            }
            """,
            {"id": product_id}
        )
        return [e["node"] for e in result["product"]["variants"]["edges"]]

    def _bulk_update_variants(self, product_id, variants_payload):
        self.client.graphql(
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

    # ==================== ADD IMAGE ====================

    def add_product_image(self, product_id, image_url):
        self.client.graphql(
            """
            mutation productCreateMedia($media: [CreateMediaInput!]!, $productId: ID!) {
              productCreateMedia(media: $media, productId: $productId) {
                media { alt mediaContentType status }
                mediaUserErrors { field message }
              }
            }
            """,
            {
                "productId": product_id,
                "media": [{"originalSource": image_url, "mediaContentType": "IMAGE"}]
            }
        )