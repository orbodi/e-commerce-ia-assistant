from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.shop.models import Category, Product

CATEGORIES = [
    ("pc-portable", "PC Portable"),
    ("accessoire", "Accessoire"),
    ("stockage", "Stockage"),
    ("peripherique", "Périphérique"),
]

PRODUCTS = [
    ("PC Portable Dell Inspiron 15", "pc-portable", 550000, 650000, "https://images.unsplash.com/photo-1593642702821-c8da6771f0c6?w=400&q=80", "Promo", 4.8, 34, 10),
    ("Souris Gamer Logitech G502", "peripherique", 45000, None, "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=400&q=80", "Best", 4.9, 56, 25),
    ("Clavier Mécanique RGB", "peripherique", 65000, 85000, "https://images.unsplash.com/photo-1595225476474-87563907a212?w=400&q=80", "Promo", 4.6, 22, 15),
    ("SSD NVMe 1To", "stockage", 85000, None, "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=400&q=80", "New", 4.7, 18, 20),
    ("Moniteur 27\" 4K", "peripherique", 320000, 380000, "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400&q=80", "Promo", 4.5, 29, 8),
    ("PC Portable HP Pavilion", "pc-portable", 480000, None, "https://images.unsplash.com/photo-1588872657578-7efd1f1555ed?w=400&q=80", "", 4.4, 41, 12),
    ("Disque Dur Externe 2To", "stockage", 75000, 99000, "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=400&q=80", "Promo", 4.3, 15, 18),
    ("Webcam HD 1080p", "peripherique", 35000, None, "https://images.unsplash.com/photo-1587826080692-f439cd0b70da?w=400&q=80", "New", 4.2, 9, 30),
    ("PC Portable Lenovo ThinkPad", "pc-portable", 620000, 720000, "https://images.unsplash.com/photo-1537498425277-c283d32ef9db?w=400&q=80", "Promo", 4.9, 47, 6),
    ("Câble HDMI 2.1", "accessoire", 12000, None, "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=400&q=80", "", 4.1, 8, 50),
    ("Station d'accueil USB-C", "accessoire", 65000, 85000, "https://images.unsplash.com/photo-1617788138017-80ad40651399?w=400&q=80", "Promo", 4.3, 12, 14),
    ("Casque Gaming HyperX", "peripherique", 89000, None, "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=400&q=80", "Best", 4.8, 63, 22),
]


class Command(BaseCommand):
    help = "Charge les catégories et produits de démonstration AFRIPUL"

    def handle(self, *args, **options):
        for slug, name in CATEGORIES:
            Category.objects.update_or_create(slug=slug, defaults={"name": name})

        created = 0
        updated = 0
        for name, cat_slug, price, old_price, image, badge, rating, reviews, stock in PRODUCTS:
            category = Category.objects.get(slug=cat_slug)
            _, was_created = Product.objects.update_or_create(
                name=name,
                defaults={
                    "category": category,
                    "price": price,
                    "old_price": old_price,
                    "image_url": image,
                    "badge": badge,
                    "rating": Decimal(str(rating)),
                    "reviews_count": reviews,
                    "stock": stock,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Produits créés: {created}, mis à jour: {updated}"))
