from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="shop_index"),
    path("api/products/", views.api_products, name="api_products"),
    path("api/orders/", views.api_create_order, name="api_create_order"),
    path("api/cart/", views.api_cart, name="api_cart"),
    path("api/cart/items/", views.api_cart_items, name="api_cart_items"),
    path("api/cart/clear/", views.api_cart_clear, name="api_cart_clear"),
    path("api/chat/", views.api_chat, name="api_chat"),
    path("api/ai/parse/", views.api_ai_parse, name="api_ai_parse"),
]
