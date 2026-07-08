from django.db import transaction

from apps.shop.models import Customer, Order, OrderItem, Product


class OrderServiceError(Exception):
    pass


@transaction.atomic
def create_order(
    *,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    customer_address: str,
    items: list[dict],
) -> Order:
    if not items:
        raise OrderServiceError("Le panier est vide.")

    customer_name = (customer_name or "").strip()
    customer_email = (customer_email or "").strip().lower()
    customer_phone = (customer_phone or "").strip()
    customer_address = (customer_address or "").strip()

    if not customer_email:
        raise OrderServiceError("Email client requis.")

    customer, _created = Customer.objects.get_or_create(
        email=customer_email,
        defaults={
            "name": customer_name or "Client",
            "phone": customer_phone,
            "address": customer_address,
        },
    )

    # Keep customer info fresh from latest checkout
    if customer_name:
        customer.name = customer_name
    customer.phone = customer_phone or customer.phone
    customer.address = customer_address or customer.address
    customer.save(update_fields=["name", "phone", "address"])

    order = Order.objects.create(
        customer=customer,
        customer_name=customer_name or "Client",
        customer_email=customer_email,
        customer_phone=customer_phone,
        customer_address=customer_address,
        status=Order.Status.PENDING,
        total=0,
    )

    total = 0
    for item in items:
        product_id = item.get("product_id")
        quantity = int(item.get("quantity", 0))
        if quantity <= 0:
            raise OrderServiceError("Quantité invalide.")

        try:
            product = Product.objects.select_for_update().get(pk=product_id, is_active=True)
        except Product.DoesNotExist as exc:
            raise OrderServiceError(f"Produit #{product_id} introuvable.") from exc

        if product.stock < quantity:
            raise OrderServiceError(f"Stock insuffisant pour {product.name}.")

        line_total = product.price * quantity
        total += line_total
        product.stock -= quantity
        product.save(update_fields=["stock"])

        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=product.price,
        )

    order.total = int(total)
    order.save(update_fields=["total"])
    return order
