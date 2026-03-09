from app.clients.shopify_client import ShopifyClient


class CollectionService:
    def __init__(self):
        self.client = ShopifyClient()

    def get_collections(self):
        """
        Fetches the first 100 collections from Shopify.
        """
        query = """
        query getCollections {
          collections(first: 100) {
            edges {
              node {
                id
                title
                handle
                description
                productsCount { count }
                image { url }
                updatedAt
              }
            }
          }
        }
        """
        data = self.client.graphql(query)
        collections = []
        for edge in data.get("collections", {}).get("edges", []):
            node = edge["node"]
            collections.append({
                "id": node["id"],
                "title": node["title"],
                "handle": node["handle"],
                "description": node["description"],
                "products_count": node.get("productsCount", {}).get("count", 0),
                "image": node.get("image", {}).get("url") if node.get("image") else None,
                "updated_at": node["updatedAt"]
            })
        return collections

    def get_collection(self, collection_id: str):
        """
        Fetches details for a single collection.
        """
        query = """
        query getCollection($id: ID!) {
          collection(id: $id) {
            id
            title
            handle
            descriptionHtml
            updatedAt
            image { url }
            products(first: 50) {
              edges {
                node {
                  id
                  title
                  featuredImage { url }
                  status
                }
              }
            }
          }
        }
        """
        data = self.client.graphql(query, {"id": collection_id})
        collection = data.get("collection")
        if not collection:
            raise Exception("Collection not found")
        
        # Format products
        products = []
        for edge in collection.get("products", {}).get("edges", []):
            pnode = edge["node"]
            products.append({
                "id": pnode["id"],
                "title": pnode["title"],
                "status": pnode["status"],
                "image": pnode.get("featuredImage", {}).get("url") if pnode.get("featuredImage") else None
            })
            
        return {
            "id": collection["id"],
            "title": collection["title"],
            "handle": collection["handle"],
            "descriptionHtml": collection["descriptionHtml"],
            "updated_at": collection["updatedAt"],
            "image": collection.get("image", {}).get("url") if collection.get("image") else None,
            "products": products
        }

    def update_collection(self, collection_id: str, title: str, description_html: str = None):
        """
        Updates a collection's title and description.
        """
        mutation = """
        mutation collectionUpdate($input: CollectionInput!) {
          collectionUpdate(input: $input) {
            collection {
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
        input_data = {
            "id": collection_id,
            "title": title
        }
        if description_html is not None:
            input_data["descriptionHtml"] = description_html
            
        data = self.client.graphql(mutation, {"input": input_data})
        errors = data.get("collectionUpdate", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Update failed: {errors[0]['message']}")
            
        return data["collectionUpdate"]["collection"]
