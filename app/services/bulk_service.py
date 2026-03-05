from app.clients.shopify_client import ShopifyClient
import time


class BulkService:

    def __init__(self):
        self.client = ShopifyClient()

    def bulk_price_update(self, percentage):

        products = self.client.get_products()

        results = {
            "total_products": len(products),
            "updated_products": 0,
            "failed_products": 0,
            "details": []
        }

        for product in products:

            product_id = product["id"]
            title = product.get("title")

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
                    continue

                mutation = """
                mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                    productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                        productVariants {
                            id
                            price
                        }
                        userErrors {
                            field
                            message
                        }
                    }
                }
                """

                variables = {
                    "productId": product_id,
                    "variants": variants_payload
                }

                response = self.client.graphql(mutation, variables)

                errors = response["productVariantsBulkUpdate"]["userErrors"]

                if errors:

                    results["failed_products"] += 1

                    results["details"].append({
                        "product_id": product_id,
                        "title": title,
                        "status": "failed",
                        "errors": errors
                    })

                else:

                    results["updated_products"] += 1

                    results["details"].append({
                        "product_id": product_id,
                        "title": title,
                        "status": "success",
                        "variants_updated": len(variants_payload)
                    })

                # 🛑 Rate limit protection
                time.sleep(0.5)

            except Exception as e:

                results["failed_products"] += 1

                results["details"].append({
                    "product_id": product_id,
                    "title": title,
                    "status": "exception",
                    "error": str(e)
                })

                time.sleep(1)

        return results