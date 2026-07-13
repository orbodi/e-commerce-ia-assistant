from decimal import Decimal

from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Badge(models.TextChoices):
        PROMO = "Promo", "Promo"
        NEW = "New", "New"
        BEST = "Best", "Best"

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.PositiveIntegerField(help_text="Prix en FCFA")
    old_price = models.PositiveIntegerField(null=True, blank=True, help_text="Ancien prix en FCFA")
    image_url = models.URLField(max_length=500)
    badge = models.CharField(max_length=10, choices=Badge.choices, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("4.0"))
    reviews_count = models.PositiveIntegerField(default=0)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.email})"


class Cart(models.Model):
    # Cart "anonymous" support: identified by session_key from the browser.
    session_key = models.CharField(max_length=64, unique=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Cart {self.session_key}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [("cart", "product")]

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"


class ChatSession(models.Model):
    """État du dialogue de commande guidée (par session navigateur)."""

    class Step(models.TextChoices):
        IDLE = "idle", "Inactif"
        COLLECT_PRODUCTS = "collect_products", "Collecte produits"
        CUSTOMER_NAME = "customer_name", "Nom client"
        CUSTOMER_EMAIL = "customer_email", "Email client"
        CUSTOMER_PHONE = "customer_phone", "Téléphone client"
        CUSTOMER_ADDRESS = "customer_address", "Adresse client"
        CONFIRM = "confirm", "Confirmation"

    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    step = models.CharField(
        max_length=32, choices=Step.choices, default=Step.IDLE
    )
    customer_name = models.CharField(max_length=150, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    customer_address = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"ChatSession {self.session_key} ({self.step})"

    def reset(self) -> None:
        self.step = self.Step.IDLE
        self.customer_name = ""
        self.customer_email = ""
        self.customer_phone = ""
        self.customer_address = ""
        self.context = {}
        self.save(
            update_fields=[
                "step",
                "customer_name",
                "customer_email",
                "customer_phone",
                "customer_address",
                "context",
                "updated_at",
            ]
        )


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Utilisateur"
        ASSISTANT = "assistant", "Assistant"

    session_key = models.CharField(max_length=64, db_index=True)
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}@{self.session_key}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        CONFIRMED = "confirmed", "Confirmée"
        SHIPPED = "shipped", "Expédiée"
        DELIVERED = "delivered", "Livrée"
        CANCELLED = "cancelled", "Annulée"

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=30)
    customer_address = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.order_number:
            self.order_number = f"AF{self.pk:06d}"
            super().save(update_fields=["order_number"])

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"
