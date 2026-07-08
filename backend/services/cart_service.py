from django.db import transaction

from apps.shop.models import Cart, CartItem, Product
from services.product_service import serialize_product


def get_or_create_cart(session_key: str) -> Cart:
    session_key = (session_key or "").strip()
    if not session_key:
        raise ValueError("session_key requis")
    cart, _ = Cart.objects.get_or_create(session_key=session_key)
    return cart


def serialize_cart(cart: Cart) -> dict:
    items_qs = (
        cart.items.select_related("product", "product__category").all()
    )
    items = []
    subtotal = 0
    for item in items_qs:
        subtotal += item.product.price * item.quantity
        items.append({**serialize_product(item.product), "qty": item.quantity})
    return {
        "cart_id": cart.id,
        "items": items,
        "subtotal": subtotal,
    }


@transaction.atomic
def update_cart_item(*, session_key: str, product_id: int, quantity_delta: int) -> dict:
    cart = get_or_create_cart(session_key)
    if quantity_delta == 0:
        return serialize_cart(cart)

    product = Product.objects.get(pk=product_id, is_active=True)
    item, _ = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": 0})
    item.quantity = item.quantity + int(quantity_delta)

    if item.quantity <= 0:
        item.delete()
    else:
        item.save(update_fields=["quantity"])

    return serialize_cart(cart)


@transaction.atomic
def clear_cart(*, session_key: str) -> dict:
    cart = get_or_create_cart(session_key)
    cart.items.all().delete()
    return serialize_cart(cart)

