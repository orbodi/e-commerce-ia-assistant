# e-commerce-ia-assistant

Assistant IA de support e-commerce local — boutique AFRIPUL.

## Démarrage rapide (local)

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_products
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000

## Démarrage avec Docker

```bash
docker compose up -d --build
```

Ouvrir http://localhost:8000

## Structure

```
backend/
├── config/          # Configuration Django
├── apps/
│   ├── core/        # Éléments communs
│   └── shop/        # Produits, commandes, boutique
├── services/        # Logique métier
├── templates/       # Templates HTML
└── static/          # CSS / JS (basé sur template.html)
```

## Fonctionnalités actuelles

- Catalogue produits avec filtres et recherche
- Panier et passage de commande (API `/api/orders/`)
- Interface chat (formulaire guidé — IA à venir)
- Admin Django : http://127.0.0.1:8000/admin/

Créer un superutilisateur :

```bash
cd backend
python manage.py createsuperuser
```
