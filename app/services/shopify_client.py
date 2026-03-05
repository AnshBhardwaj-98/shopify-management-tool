import requests
from app.core.config import settings


class ShopifyClient:
    def __init__(self):
        self.base_url = f"https://{settings.SHOPIFY_STORE}/admin/api/{settings.API_VERSION}/graphql.json"
        self.headers = {
            "X-Shopify-Access-Token": settings.SHOPIFY_TOKEN,
            "Content-Type": "application/json",
        }

    def graphql(self, query: str, variables: dict = None):
        response = requests.post(
            self.base_url,
            json={"query": query, "variables": variables},
            headers=self.headers,
        )

        if response.status_code != 200:
            raise Exception(
                f"Shopify API error: {response.status_code} - {response.text}"
            )

        data = response.json()

        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")

        return data["data"]

    # 👇 ADD THIS METHOD INSIDE THE CLASS
    def get_products(self):
        all_products = []
        cursor = None
        has_next_page = True

        while has_next_page:
            query = """
            query ($cursor: String) {
            products(first: 250, after: $cursor) {
                pageInfo {
                hasNextPage
                }
                edges {
                cursor
                node {
                    id
                    title
                    vendor
                    productType
                    variants(first: 50) {
                    edges {
                        node {
                        id
                        price
                        }
                    }
                    }
                }
                }
            }
            }
            """

            variables = {"cursor": cursor}

            data = self.graphql(query, variables)
            products_data = data["products"]

            for edge in products_data["edges"]:
                all_products.append(edge["node"])
                cursor = edge["cursor"]

            has_next_page = products_data["pageInfo"]["hasNextPage"]

        return all_products
    
    def update_product_title(self, product_id: str, new_title: str):
        mutation = """
        mutation updateProduct($input: ProductInput!) {
        productUpdate(input: $input) {
            product {
            id
            title
            }
            userErrors {
            field
            message
            }
        }
        }
        """

        variables = {
            "input": {
                "id": product_id,
                "title": new_title
            }
        }

        return self.graphql(mutation, variables)
    

    def update_variant_price(self, product_id: str, variant_id: str, new_price: float):
        mutation = """
        mutation updateVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
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
            "variants": [
                {
                    "id": variant_id,
                    "price": str(new_price)
                }
            ]
        }

        return self.graphql(mutation, variables)
    

    def bulk_update_prices_by_percentage(self, percentage: float):
        products = self.get_products()

        results = []

        for product in products:
            product_id = product["id"]

            variants_to_update = []

            for v_edge in product["variants"]["edges"]:
                variant = v_edge["node"]
                old_price = float(variant["price"])
                new_price = round(old_price * (1 + percentage / 100), 2)

                variants_to_update.append({
                    "id": variant["id"],
                    "price": str(new_price)
                })

            if not variants_to_update:
                continue

            mutation = """
            mutation bulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
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
                "variants": variants_to_update
            }

            response = self.graphql(mutation, variables)
            results.append(response)

        return results





























