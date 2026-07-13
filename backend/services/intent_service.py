"""Extraction d'intention + entités (heuristiques rapides, LLM en secours)."""

import json
import re

from services.llm_config import LLMServiceError, llm_model, llm_timeout
from services.llm_prompt import INTENT_SYSTEM_PROMPT
from services.llm_service import llm_chat, safe_extract_message_content
from services.product_service import QUERY_TO_CATEGORY, search_products_ranked

INTENTS = {
    "greeting",
    "list_products",
    "search_product",
    "check_stock",
    "create_order",
    "checkout",
    "view_cart",
    "track_order",
    "unknown",
}


def _word_to_int(word: str) -> int | None:
    mapping = {
        "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
        "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    }
    return mapping.get((word or "").strip().lower())


def _extract_quantity(message: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\b", message)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    for w in ("dix", "neuf", "huit", "sept", "six", "cinq", "quatre", "trois", "deux", "un", "une"):
        if re.search(rf"\b{w}\b", message.lower()):
            v = _word_to_int(w)
            if v:
                return v
    return None


def _extract_order_number(message: str) -> str | None:
    m = re.search(r"\bAF\d{6}\b", message.upper())
    return m.group(0) if m else None


def _is_greeting(low: str) -> bool:
    words = set(re.sub(r"[^\w\s']", " ", low).split())
    return bool(words & {"bonjour", "salut", "coucou", "bonsoir", "hello", "hi", "hey"})


def _is_checkout_request(low: str) -> bool:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", low)).strip()
    if normalized in {"commande", "une commande", "ma commande", "la commande", "commander", "acheter"}:
        return True
    if re.search(r"\bcomm[ae]nd(?:er|e|é|é)?\b", low):
        remainder = re.sub(r"\bcomm[ae]nd(?:er|e|é|é)?\b", " ", low).strip()
        if not remainder or remainder in {"une", "un", "ma", "la"}:
            return True
    phrases = (
        "passer une commande", "passer commande", "je veux commander",
        "valider commande", "valider le panier", "finaliser commande", "checkout", "payer",
    )
    return any(p in low for p in phrases)


def _is_list_products_request(low: str) -> bool:
    patterns = (
        r"\bliste(?:r|z)?\b",
        r"\btous\b.*\bproduits?\b",
        r"\bcatalogue\b",
        r"\bquels?\s+(?:sont\s+)?(?:les?\s+)?produits?\b",
    )
    return any(re.search(p, low) for p in patterns)


def _is_check_stock_request(low: str) -> bool:
    if _is_list_products_request(low):
        return False
    return any(k in low for k in ("stock", "rupture", "disponibilite", "dispo", "disponible"))


def _clean_product_query(low: str) -> str:
    cleaned = re.sub(
        r"\b(\d{1,3}|un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b",
        " ", low, flags=re.I,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _heuristic_parse(message: str) -> dict:
    text = (message or "").strip()
    low = text.lower()

    if _is_greeting(low):
        return {"intent": "greeting", "entities": {}}

    order_number = _extract_order_number(text)
    if order_number:
        return {"intent": "track_order", "entities": {"order_number": order_number}}

    if _is_checkout_request(low):
        return {"intent": "checkout", "entities": {}}

    if any(k in low for k in ("panier", "mon panier", "voir panier", "vérifie", "verifie")):
        return {"intent": "view_cart", "entities": {}}

    if _is_list_products_request(low):
        return {"intent": "list_products", "entities": {}}

    qty = _extract_quantity(text) or 1

    if _is_check_stock_request(low):
        cleaned = _clean_product_query(
            re.sub(r"\b(stock|disponible|rupture|disponibilite|dispo)\b", " ", low, flags=re.I)
        )
        if cleaned:
            return {
                "intent": "check_stock",
                "entities": {"products": [{"product_query": cleaned, "quantity": qty}]},
            }

    if low.strip() in QUERY_TO_CATEGORY:
        return {
            "intent": "search_product",
            "entities": {"products": [{"product_query": low.strip(), "quantity": qty}]},
        }

    cleaned = _clean_product_query(low) or text
    return {
        "intent": "search_product",
        "entities": {"products": [{"product_query": cleaned, "quantity": qty}]},
    }


def _extract_strict_json(text: str) -> dict | None:
    if not isinstance(text, str):
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_llm_result(data: dict) -> dict | None:
    if not data or data.get("intent") not in INTENTS:
        return None
    entities = data.get("entities") or {}
    if not isinstance(entities, dict):
        entities = {}
    products = entities.get("products")
    if isinstance(products, list):
        norm = []
        for p in products:
            if not isinstance(p, dict):
                continue
            pq = (p.get("product_query") or "").strip()
            q = p.get("quantity", 1)
            try:
                q = max(1, int(q))
            except (TypeError, ValueError):
                q = 1
            if pq:
                norm.append({"product_query": pq, "quantity": q})
        entities["products"] = norm
    data["entities"] = entities
    return data


def extract_intent_and_entities(message: str) -> dict:
    """
    Heuristiques d'abord (réponse instantanée).
    LLM uniquement pour les requêtes produit ambiguës.
    """
    heuristic = _heuristic_parse(message)
    fast_intents = {
        "greeting", "list_products", "check_stock", "create_order",
        "checkout", "view_cart", "track_order",
    }
    if heuristic.get("intent") in fast_intents:
        return heuristic

    sys = INTENT_SYSTEM_PROMPT

    try:
        payload = llm_chat(
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": message},
            ],
            model=llm_model(),
            timeout=llm_timeout(),
        )
        content = safe_extract_message_content(payload)
        data = _normalize_llm_result(_extract_strict_json(content) or {})
        if data:
            return data
    except LLMServiceError:
        pass

    return heuristic
