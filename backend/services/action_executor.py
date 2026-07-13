from dataclasses import dataclass, field

from apps.shop.models import Order, Product
from services.cart_service import clear_cart, get_or_create_cart, serialize_cart, set_cart_item_quantity, update_cart_item
from services.order_service import OrderServiceError, create_order
from services.product_service import get_all_products, search_products, search_products_ranked

CATEGORY_SEARCH_HINTS = {
    "accessoire": "accessoire",
    "accessoires": "accessoire",
    "peripherique": "peripherique",
    "périphérique": "peripherique",
    "peripheriques": "peripherique",
    "périphériques": "peripherique",
    "pc": "pc-portable",
    "ordinateur": "pc-portable",
    "ordi": "pc-portable",
    "stockage": "stockage",
}


@dataclass
class ActionResult:
    success: bool
    reply: str
    intent: str = "unknown"
    actions: list = field(default_factory=list)


def _format_price(price: int) -> str:
    return f"{price:,} FCFA".replace(",", "\u202f")


def _find_product(*, product_id: int | None = None, product_query: str = "") -> Product | None:
    if product_id:
        try:
            return Product.objects.select_related("category").get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            return None

    query = (product_query or "").strip()
    if not query:
        return None

    matches = search_products(query=query)
    if not matches:
        return None
    try:
        return Product.objects.select_related("category").get(pk=matches[0]["id"], is_active=True)
    except Product.DoesNotExist:
        return None


def execute_action(action: dict, *, session_key: str) -> ActionResult:
    action_type = (action or {}).get("type", "")
    if not action_type:
        return ActionResult(False, "Action inconnue.", intent="unknown")

    if action_type == "list_products":
        limit = action.get("limit", 10)
        try:
            limit = max(1, min(50, int(limit)))
        except (TypeError, ValueError):
            limit = 10
        products = get_all_products()[:limit]
        if not products:
            return ActionResult(True, "Le catalogue est vide pour le moment.", intent="list_products")
        lines = [
            f"• <strong>{p['name']}</strong> — {_format_price(p['price'])} (stock: {p['stock']})"
            for p in products
        ]
        return ActionResult(
            True,
            "📦 <strong>Catalogue</strong> :<br>" + "<br>".join(lines),
            intent="list_products",
        )

    if action_type == "search_products":
        query = (action.get("product_query") or "").strip()
        if not query:
            return ActionResult(False, "Indiquez le nom du produit recherché.", intent="search_products")
        low = query.lower()
        if low in CATEGORY_SEARCH_HINTS:
            matches = search_products(category_slug=CATEGORY_SEARCH_HINTS[low])
        else:
            matches = search_products_ranked(query, limit=5)
        if not matches:
            return ActionResult(
                False,
                f"Aucun produit trouvé pour « {query} ».",
                intent="search_products",
            )
        lines = [
            f"• id={p['id']} — <strong>{p['name']}</strong> — {_format_price(p['price'])} (stock: {p['stock']})"
            for p in matches
        ]
        return ActionResult(
            True,
            "🔍 <strong>Résultats</strong> :<br>" + "<br>".join(lines),
            intent="search_products",
        )

    if action_type == "check_stock":
        product = _find_product(
            product_id=action.get("product_id"),
            product_query=action.get("product_query", ""),
        )
        if not product:
            return ActionResult(False, "Produit introuvable.", intent="check_stock")
        if product.stock > 0:
            reply = (
                f"✅ <strong>{product.name}</strong> est disponible "
                f"({product.stock} en stock) — {_format_price(product.price)}."
            )
        else:
            reply = f"❌ <strong>{product.name}</strong> est en rupture de stock."
        return ActionResult(True, reply, intent="check_stock")

    if action_type == "add_to_cart":
        product = _find_product(
            product_id=action.get("product_id"),
            product_query=action.get("product_query", ""),
        )
        if not product:
            return ActionResult(False, "Produit introuvable pour l'ajout au panier.", intent="add_to_cart")
        try:
            quantity = max(1, int(action.get("quantity", 1)))
        except (TypeError, ValueError):
            quantity = 1
        if product.stock < quantity:
            return ActionResult(
                False,
                f"Stock insuffisant pour <strong>{product.name}</strong> "
                f"(demandé: {quantity}, disponible: {product.stock}).",
                intent="add_to_cart",
            )
        update_cart_item(
            session_key=session_key,
            product_id=product.id,
            quantity_delta=quantity,
        )
        return ActionResult(
            True,
            f"✅ <strong>{product.name}</strong> x{quantity} ajouté au panier.",
            intent="add_to_cart",
            actions=[{"type": "cart_updated", "product_id": product.id}],
        )

    if action_type == "update_cart":
        product = _find_product(
            product_id=action.get("product_id"),
            product_query=action.get("product_query", ""),
        )
        if not product:
            return ActionResult(False, "Produit introuvable dans le panier.", intent="update_cart")
        try:
            quantity = max(0, int(action.get("quantity", 0)))
        except (TypeError, ValueError):
            return ActionResult(False, "Quantité invalide.", intent="update_cart")
        set_cart_item_quantity(session_key=session_key, product_id=product.id, quantity=quantity)
        if quantity == 0:
            msg = f"✅ <strong>{product.name}</strong> retiré du panier."
        else:
            msg = f"✅ <strong>{product.name}</strong> mis à jour : x{quantity}."
        cart = serialize_cart(get_or_create_cart(session_key))
        if cart["items"]:
            lines = [
                f"• <strong>{i['name']}</strong> x{i['qty']} — {_format_price(i['price'] * i['qty'])}"
                for i in cart["items"]
            ]
            msg += "<br><br>🛒 <strong>Panier</strong> :<br>" + "<br>".join(lines)
            msg += f"<br><br><strong>Total : {_format_price(cart['subtotal'])}</strong>"
        else:
            msg += "<br><br>🛒 Votre panier est vide."
        return ActionResult(True, msg, intent="update_cart", actions=[{"type": "cart_updated"}])

    if action_type == "view_cart":
        cart = serialize_cart(get_or_create_cart(session_key))
        if not cart["items"]:
            return ActionResult(True, "🛒 Votre panier est vide.", intent="view_cart")
        lines = [
            f"• <strong>{item['name']}</strong> x{item['qty']} — "
            f"{_format_price(item['price'] * item['qty'])}"
            for item in cart["items"]
        ]
        reply = (
            "🛒 <strong>Votre panier</strong> :<br>"
            + "<br>".join(lines)
            + f"<br><br><strong>Total : {_format_price(cart['subtotal'])}</strong>"
        )
        return ActionResult(True, reply, intent="view_cart")

    if action_type == "track_order":
        order_number = (action.get("order_number") or "").strip().upper()
        if not order_number:
            return ActionResult(
                False,
                "Indiquez le numéro de commande (ex: AF000001).",
                intent="track_order",
            )
        try:
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            return ActionResult(
                False,
                f"Commande <strong>{order_number}</strong> introuvable.",
                intent="track_order",
            )
        status_label = order.get_status_display()
        reply = (
            f"📦 Commande <strong>{order.order_number}</strong><br>"
            f"Statut : <strong>{status_label}</strong><br>"
            f"Total : {_format_price(order.total)}<br>"
            f"Client : {order.customer_name}"
        )
        return ActionResult(True, reply, intent="track_order")

    if action_type == "place_order":
        cart = serialize_cart(get_or_create_cart(session_key))
        if not cart["items"]:
            return ActionResult(False, "Le panier est vide.", intent="place_order")

        items = [{"product_id": item["id"], "quantity": item["qty"]} for item in cart["items"]]
        try:
            order = create_order(
                customer_name=action.get("customer_name", "Client"),
                customer_email=action.get("customer_email", "client@afripul.tg"),
                customer_phone=action.get("customer_phone", ""),
                customer_address=action.get("customer_address", ""),
                items=items,
            )
        except OrderServiceError as exc:
            return ActionResult(False, str(exc), intent="place_order")

        clear_cart(session_key=session_key)
        reply = (
            f"✅ Commande <strong>#{order.order_number}</strong> enregistrée !<br>"
            f"Total : <strong>{_format_price(order.total)}</strong><br>"
            "Merci pour votre confiance ! 🙏"
        )
        return ActionResult(
            True,
            reply,
            intent="order_confirmed",
            actions=[
                {"type": "order_created", "order_number": order.order_number, "total": order.total},
                {"type": "cart_updated"},
            ],
        )

    return ActionResult(False, f"Action non supportée : {action_type}", intent="unknown")
