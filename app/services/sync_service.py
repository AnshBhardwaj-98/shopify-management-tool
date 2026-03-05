from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.variant import Variant
from app.services.shopify_client import ShopifyClient
from datetime import datetime


def sync_products(db: Session):
    client = ShopifyClient()
    products = client.fetch_all_products()

    for p in products:
        product = Product(
            id=p["id"],
            title=p["title"],
            vendor=p.get("vendor"),
            product_type=p.get("productType"),
            updated_at=datetime.utcnow(),
        )

        db.merge(product)

        for v_edge in p["variants"]["edges"]:
            v = v_edge["node"]

            variant = Variant(
                id=v["id"],
                product_id=p["id"],
                price=float(v["price"]),
                updated_at=datetime.utcnow(),
            )

            db.merge(variant)

    db.commit()

    return len(products)