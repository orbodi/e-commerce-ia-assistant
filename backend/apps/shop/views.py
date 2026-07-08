import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from services.cart_service import clear_cart, update_cart_item, get_or_create_cart, serialize_cart
from services.order_service import OrderServiceError, create_order
from services.product_service import get_all_products, search_products
from apps.shop.models import Product


def index(request):
    products = get_all_products()
    categories = sorted({p["category"] for p in products})
    return render(
        request,
        "shop/index.html",
        {
            "products_json": json.dumps(products),
            "categories": categories,
        },
    )


@require_GET
def api_products(request):
    query = request.GET.get("q", "")
    category = request.GET.get("category", "all")
    products = search_products(query=query, category_slug=category)
    return JsonResponse({"products": products})


@require_POST
@csrf_exempt
def api_create_order(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide."}, status=400)

    try:
        order = create_order(
            customer_name=payload.get("customer_name", "Client"),
            customer_email=payload.get("customer_email", "client@afripul.tg"),
            customer_phone=payload.get("customer_phone", ""),
            customer_address=payload.get("customer_address", ""),
            items=payload.get("items", []),
        )
    except OrderServiceError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(
        {
            "order_number": order.order_number,
            "total": order.total,
            "status": order.status,
        }
    )


@require_GET
def api_cart(request):
    session_key = request.GET.get("session_key", "")
    try:
        cart = get_or_create_cart(session_key)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(serialize_cart(cart))


@require_POST
@csrf_exempt
def api_cart_items(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide."}, status=400)

    session_key = payload.get("session_key", "")
    product_id = payload.get("product_id", None)
    quantity_delta = payload.get("quantity_delta", 0)

    if product_id is None:
        return JsonResponse({"error": "product_id requis."}, status=400)

    try:
        cart_data = update_cart_item(
            session_key=session_key,
            product_id=int(product_id),
            quantity_delta=int(quantity_delta),
        )
    except (ValueError, Product.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(cart_data)


@require_POST
@csrf_exempt
def api_cart_clear(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide."}, status=400)

    session_key = payload.get("session_key", "")
    try:
        cart_data = clear_cart(session_key=session_key)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(cart_data)
