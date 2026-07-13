import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from services.cart_service import clear_cart, update_cart_item, get_or_create_cart, serialize_cart
from services.chat_service import process_chat_message
from services.intent_service import extract_intent_and_entities
from services.order_service import OrderServiceError, create_order
from services.product_service import get_all_products, search_products, search_products_ranked
from apps.shop.models import Product, Order


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


@require_POST
@csrf_exempt
def api_chat(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide."}, status=400)

    message = payload.get("message", "")
    session_key = payload.get("session_key", "")

    if not session_key:
        return JsonResponse({"error": "session_key requis."}, status=400)

    result = process_chat_message(message=message, session_key=session_key)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


@require_POST
@csrf_exempt
def api_ai_parse(request):
    """Parse un message => intent + entities (+ résolution produits)."""
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON invalide."}, status=400)

    message = payload.get("message", "")
    data = extract_intent_and_entities(message)
    intent = data.get("intent", "unknown")
    entities = data.get("entities") or {}

    resolved_products = []
    products = entities.get("products")
    if isinstance(products, list):
        for p in products:
            if not isinstance(p, dict):
                continue
            q = (p.get("product_query") or "").strip()
            qty = p.get("quantity", 1)
            try:
                qty = max(1, int(qty))
            except (TypeError, ValueError):
                qty = 1
            if not q:
                continue
            matches = search_products_ranked(q, limit=3)
            if matches:
                top = matches[0]
                resolved_products.append({**top, "quantity": qty})

    order_number = entities.get("order_number")
    order_status = None
    if isinstance(order_number, str) and order_number:
        order = Order.objects.filter(order_number=order_number).first()
        if order:
            order_status = order.status

    return JsonResponse(
        {
            "intent": intent,
            "entities": entities,
            "products_resolved": resolved_products,
            "order_status": order_status,
            "order_number": order_number,
        },
        json_dumps_params={"ensure_ascii": False},
    )
