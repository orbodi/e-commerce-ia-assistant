from difflib import SequenceMatcher

from apps.shop.models import Product

QUERY_TO_CATEGORY = {
    "ordi": "pc-portable",
    "ordinateur": "pc-portable",
    "pc": "pc-portable",
    "laptop": "pc-portable",
    "portable": "pc-portable",
    "souris": "peripherique",
    "clavier": "peripherique",
    "casque": "peripherique",
    "moniteur": "peripherique",
    "ecran": "peripherique",
    "écran": "peripherique",
    "webcam": "peripherique",
    "ssd": "stockage",
    "disque": "stockage",
    "stockage": "stockage",
    "cable": "accessoire",
    "câble": "accessoire",
    "hdmi": "accessoire",
}


def serialize_product(product: Product) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category.slug,
        "price": product.price,
        "oldPrice": product.old_price,
        "image": product.image_url,
        "badge": product.badge or None,
        "rating": float(product.rating),
        "reviews": product.reviews_count,
        "stock": product.stock,
    }


def get_all_products() -> list[dict]:
    products = Product.objects.select_related("category").filter(is_active=True)
    return [serialize_product(p) for p in products]


def search_products(query: str = "", category_slug: str | None = None) -> list[dict]:
    products = Product.objects.select_related("category").filter(is_active=True)
    if category_slug and category_slug != "all":
        products = products.filter(category__slug=category_slug)
    if query:
        products = products.filter(name__icontains=query)
    return [serialize_product(p) for p in products]


def search_products_ranked(query: str, *, limit: int = 5) -> list[dict]:
    """Recherche produits avec score de similarité."""
    q = (query or "").strip().lower()
    if not q:
        return get_all_products()[:limit]

    category_slug = QUERY_TO_CATEGORY.get(q)
    if category_slug:
        matches = search_products(category_slug=category_slug)
        if matches:
            return matches[:limit]

    all_products = get_all_products()
    scored: list[tuple[float, dict]] = []
    for p in all_products:
        name = p["name"].lower()
        score = 0.0
        if q in name or name in q:
            score = 1.0
        else:
            score = SequenceMatcher(None, q, name).ratio()
        if score >= 0.35:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


def is_ambiguous_product_query(query: str, matches: list[dict]) -> bool:
    if len(matches) <= 1:
        return False
    q = (query or "").strip().lower()
    if not q:
        return True
    return not any(q in m["name"].lower() or m["name"].lower() in q for m in matches[:2])
