from app.clients.shopify_client import ShopifyClient


class InventoryService:
    def __init__(self):
        self.client = ShopifyClient()

    def get_inventory_levels(self):
        """
        Fetches inventory items and their levels across locations.
        """
        query = """
        query getInventory($cursor: String) {
          products(first: 50, after: $cursor) {
            edges {
              node {
                id
                title
                featuredImage { url }
                variants(first: 10) {
                  edges {
                    node {
                      id
                      title
                      sku
                      inventoryItem {
                        id
                        tracked
                        inventoryLevels(first: 5) {
                          edges {
                            node {
                              id
                              quantities(names: ["available"]) {
                                name
                                quantity
                              }
                              updatedAt
                              location {
                                id
                                name
                              }
                            }
                          }
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
        data = self.client.graphql(query, {"cursor": None})
        inventory_list = []

        for p_edge in data.get("products", {}).get("edges", []):
            product = p_edge["node"]
            p_title = product["title"]
            p_img = product.get("featuredImage", {}).get("url") if product.get("featuredImage") else None

            for v_edge in product.get("variants", {}).get("edges", []):
                variant = v_edge["node"]
                inv_item = variant.get("inventoryItem", {})
                if not inv_item:
                    continue

                levels = []
                for l_edge in inv_item.get("inventoryLevels", {}).get("edges", []):
                    level = l_edge["node"]
                    location = level.get("location") or {}

                    # API 2024-01+: quantities array replaces `available` field
                    available = None
                    for q in level.get("quantities", []):
                        if q["name"] == "available":
                            available = q["quantity"]
                            break

                    levels.append({
                        "id": level["id"],
                        "available": available,
                        "updated_at": level["updatedAt"],
                        "location_id": location.get("id"),
                        "location_name": location.get("name"),
                    })

                inventory_list.append({
                    "product_id": product["id"],
                    "variant_id": variant["id"],
                    "inventory_item_id": inv_item["id"],
                    "product_title": p_title,
                    "variant_title": variant["title"],
                    "sku": variant.get("sku", ""),
                    "image": p_img,
                    "tracked": inv_item.get("tracked", False),
                    "levels": levels,
                })

        return inventory_list

    def adjust_inventory(self, inventory_item_id: str, location_id: str, available_delta: int, current_quantity: int = 0):
        """
        Sets the available quantity of an inventory item at a specific location.
        Uses inventorySetQuantities (replaces deprecated inventoryAdjustQuantity).
        current_quantity is passed from the frontend to avoid an extra query.
        """
        new_quantity = current_quantity + available_delta

        # Step 2: set the new absolute quantity
        mutation = """
        mutation inventorySet($input: InventorySetQuantitiesInput!) {
          inventorySetQuantities(input: $input) {
            inventoryAdjustmentGroup {
              reason
              changes {
                name
                delta
                quantityAfterChange
              }
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
                "name": "available",
                "reason": "correction",
                "ignoreCompareQuantity": True,
                "quantities": [
                    {
                        "inventoryItemId": inventory_item_id,
                        "locationId": location_id,
                        "quantity": new_quantity,
                    }
                ],
            }
        }

        result = self.client.graphql(mutation, variables)
        errors = result.get("inventorySetQuantities", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Inventory update failed: {errors[0]['message']}")

        # Return the new available quantity
        changes = result.get("inventorySetQuantities", {}).get("inventoryAdjustmentGroup", {}).get("changes", [])
        for change in changes:
            if change["name"] == "available":
                return {"available": change["quantityAfterChange"]}

        return {"available": new_quantity}