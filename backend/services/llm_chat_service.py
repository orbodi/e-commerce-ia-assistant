import json
import re

from apps.shop.models import ChatMessage, ChatSession, Product
from services.action_executor import execute_action
from services.cart_service import clear_cart, get_or_create_cart, serialize_cart, set_cart_item_quantity
from services.llm_config import LLMServiceError, llm_chat_enabled, llm_max_history, llm_model
from services.llm_prompt import (
    DEFAULT_TURN_CONTEXT,
    SYSTEM_PROMPT_TEMPLATE,
    TURN_CONTEXT_TEMPLATE,
)
from services.llm_service import llm_chat, safe_extract_message_content
from services.product_service import get_all_products

MAX_HISTORY = llm_max_history()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s\-.]{8,}$")
ORDER_RE = re.compile(r"\b(AF\d{6})\b", re.I)

GREETING_WORDS = frozenset({
    "bonjour", "salut", "hello", "hi", "hey", "coucou", "bonsoir", "yo",
    "bonne", "journée", "journee", "bonne journée", "bonne journee",
})

CATALOG_PHRASES = (
    "liste",
    "catalogue",
    "tous les produits",
    "tout le catalogue",
    "quels produits",
    "produits disponibles",
    "voir le catalogue",
    "montre les produits",
    "liste moi",
    "liste-moi",
)

CHECKOUT_WORDS = (
    "commander",
    "passer commande",
    "passer une commande",
    "je veux commander",
    "acheter",
    "valider commande",
)

AFFIRMATIVE_ONLY = frozenset({
    "oui", "yes", "ok", "d'accord", "daccord", "bien sûr", "bien sur",
    "bien sure", "sure", "bien sûre", "certainement", "absolument", "d'accord",
})

GENERIC_SEARCH_TERMS = frozenset({
    "accessoire", "accessoires", "ordinateur", "ordinateurs", "pc", "pcs",
    "peripherique", "peripheriques", "périphérique", "périphériques",
    "stockage", "produit", "produits",
})

MODIFY_CART_PHRASES = (
    "modifier le panier", "modifier panier", "modifier ma commande",
    "changer le panier", "changer panier", "mettre à jour le panier",
    "mettre a jour le panier", "corriger le panier",
)

CUSTOMER_STEPS = frozenset({
    ChatSession.Step.CUSTOMER_NAME,
    ChatSession.Step.CUSTOMER_EMAIL,
    ChatSession.Step.CUSTOMER_PHONE,
    ChatSession.Step.CUSTOMER_ADDRESS,
    ChatSession.Step.CONFIRM,
})


def _format_price(price: int) -> str:
    return f"{price:,} FCFA".replace(",", "\u202f")


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").lower()


def _get_chat_session(session_key: str) -> ChatSession:
    session, _ = ChatSession.objects.get_or_create(session_key=session_key)
    return session


def _get_history(session_key: str) -> list[ChatMessage]:
    return list(
        ChatMessage.objects.filter(session_key=session_key)
        .order_by("-created_at")[:MAX_HISTORY]
        [::-1]
    )


def _save_message(session_key: str, role: str, content: str) -> None:
    ChatMessage.objects.create(session_key=session_key, role=role, content=content)


def _last_assistant_text(session_key: str) -> str:
    msg = (
        ChatMessage.objects.filter(session_key=session_key, role=ChatMessage.Role.ASSISTANT)
        .order_by("-created_at")
        .first()
    )
    return msg.content if msg else ""


def clear_conversation(session_key: str) -> None:
    ChatMessage.objects.filter(session_key=session_key).delete()
    try:
        session = ChatSession.objects.get(session_key=session_key)
        session.reset()
    except ChatSession.DoesNotExist:
        pass


def _build_catalog_text() -> str:
    lines = []
    for p in get_all_products():
        lines.append(
            f"- id={p['id']} | {p['name']} | {_format_price(p['price'])} | stock={p['stock']}"
        )
    return "\n".join(lines) if lines else "(catalogue vide)"


def _build_cart_text(session_key: str) -> str:
    cart = serialize_cart(get_or_create_cart(session_key))
    if not cart["items"]:
        return "(panier vide)"
    lines = [
        f"- id={item['id']} | {item['name']} x{item['qty']} | {_format_price(item['price'] * item['qty'])}"
        for item in cart["items"]
    ]
    return "\n".join(lines) + f"\nTotal: {_format_price(cart['subtotal'])}"


def _build_checkout_state(session: ChatSession) -> str:
    if session.step == ChatSession.Step.IDLE:
        return "Aucune commande guidée en cours."

    step_labels = {
        ChatSession.Step.COLLECT_PRODUCTS: "Collecte des produits",
        ChatSession.Step.CUSTOMER_NAME: "En attente du nom du client",
        ChatSession.Step.CUSTOMER_EMAIL: "En attente de l'email",
        ChatSession.Step.CUSTOMER_PHONE: "En attente du téléphone",
        ChatSession.Step.CUSTOMER_ADDRESS: "En attente de l'adresse",
        ChatSession.Step.CONFIRM: "En attente de confirmation finale",
    }
    lines = [f"Étape : {step_labels.get(session.step, session.step)}"]
    if session.customer_name:
        lines.append(f"Nom déjà collecté : {session.customer_name}")
    if session.customer_email:
        lines.append(f"Email déjà collecté : {session.customer_email}")
    if session.customer_phone:
        lines.append(f"Téléphone déjà collecté : {session.customer_phone}")
    if session.customer_address:
        lines.append(f"Adresse déjà collectée : {session.customer_address}")
    return "\n".join(lines)


def _is_greeting_message(text: str) -> bool:
    low = text.lower().strip()
    cleaned = re.sub(r"[^\w\s'-]", "", low).strip()
    if not cleaned:
        return False
    if cleaned in GREETING_WORDS:
        return True
    words = cleaned.split()
    if len(words) <= 4 and all(w in GREETING_WORDS or w in {"je", "suis", "bon"} for w in words):
        return True
    return bool(re.match(r"^(bonjour|salut|hello|hi|hey|coucou|bonsoir)\b", cleaned))


def _wants_checkout(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in CHECKOUT_WORDS)


def _explicit_catalog_request(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in CATALOG_PHRASES)


def _is_affirmative_only(text: str) -> bool:
    low = re.sub(r"[^\w\s']", "", (text or "").lower()).strip()
    return low in AFFIRMATIVE_ONLY or low in {"bien sur", "bien sure"}


def _message_has_quantity(text: str) -> bool:
    return bool(re.search(r"\b(\d{1,3})\b", text or ""))


def _wants_modify_cart(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in MODIFY_CART_PHRASES)


def _handle_modify_cart_request(session_key: str) -> dict:
    cart = serialize_cart(get_or_create_cart(session_key))
    if not cart["items"]:
        return {
            "reply": "Votre panier est vide. Indiquez un produit à ajouter.",
            "intent": "view_cart",
            "entities": {},
            "actions": [],
        }
    lines = [
        f"• <strong>{i['name']}</strong> x{i['qty']} — {_format_price(i['price'] * i['qty'])}"
        for i in cart["items"]
    ]
    reply = (
        "Voici votre panier. Pour le modifier :<br>"
        "• <strong>Changer la quantité</strong> : « 2 webcams » ou « mettre 3 souris »<br>"
        "• <strong>Retirer un article</strong> : « retirer la webcam »<br>"
        "• <strong>Vider</strong> : « vider le panier »<br><br>"
        "🛒 <strong>Panier actuel</strong> :<br>"
        + "<br>".join(lines)
        + f"<br><br><strong>Total : {_format_price(cart['subtotal'])}</strong>"
    )
    return {"reply": reply, "intent": "view_cart", "entities": {}, "actions": []}


def _try_cart_modification(text: str, session_key: str) -> dict | None:
    """Retire ou met à jour la quantité sans passer par le LLM."""
    low = text.lower().strip()
    cart = serialize_cart(get_or_create_cart(session_key))
    if not cart["items"]:
        return None

    if any(p in low for p in ("vider le panier", "vider panier", "supprimer tout")):
        clear_cart(session_key=session_key)
        return {
            "reply": "🛒 Panier vidé. Que souhaitez-vous commander ?",
            "intent": "update_cart",
            "entities": {},
            "actions": [{"type": "cart_updated"}],
        }

    if low.startswith("retirer ") or low.startswith("supprimer "):
        query = re.sub(r"^(retirer|supprimer)\s+", "", low).strip()
        for item in cart["items"]:
            if query in item["name"].lower() or item["name"].lower() in query:
                set_cart_item_quantity(session_key=session_key, product_id=item["id"], quantity=0)
                return {
                    "reply": f"✅ <strong>{item['name']}</strong> retiré du panier.",
                    "intent": "update_cart",
                    "entities": {},
                    "actions": [{"type": "cart_updated"}],
                }

    qty_m = re.search(r"\b(\d{1,3})\b", text)
    if qty_m:
        qty = int(qty_m.group(1))
        remainder = re.sub(r"\b\d{1,3}\b", "", low).strip()
        for item in cart["items"]:
            name_low = item["name"].lower()
            if remainder and (remainder in name_low or name_low in remainder or "webcam" in remainder and "webcam" in name_low):
                set_cart_item_quantity(session_key=session_key, product_id=item["id"], quantity=qty)
                return {
                    "reply": f"✅ Quantité mise à jour : <strong>{item['name']}</strong> x{qty}.",
                    "intent": "update_cart",
                    "entities": {},
                    "actions": [{"type": "cart_updated"}],
                }
        matches = [p for p in get_all_products() if remainder and remainder in p["name"].lower()]
        if len(matches) == 1:
            set_cart_item_quantity(session_key=session_key, product_id=matches[0]["id"], quantity=qty)
            return {
                "reply": f"✅ <strong>{matches[0]['name']}</strong> x{qty} ajouté au panier.",
                "intent": "add_to_cart",
                "entities": {},
                "actions": [{"type": "cart_updated", "product_id": matches[0]["id"]}],
            }
    return None


def _valid_product_id(product_id) -> bool:
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return False
    return Product.objects.filter(pk=pid, is_active=True).exists()


def _sync_checkout_step(session: ChatSession, user_message: str) -> None:
    """Avance l'étape de commande guidée sans capturer les salutations comme nom."""
    text = (user_message or "").strip()
    if not text:
        return

    if _is_greeting_message(text) and session.step != ChatSession.Step.IDLE:
        session.reset()
        return

    if _wants_checkout(text):
        cart = serialize_cart(get_or_create_cart(session.session_key))
        session.step = (
            ChatSession.Step.CUSTOMER_NAME
            if cart["items"]
            else ChatSession.Step.COLLECT_PRODUCTS
        )
        session.save(update_fields=["step", "updated_at"])
        return

    if session.step == ChatSession.Step.CUSTOMER_NAME:
        if _is_greeting_message(text):
            return
        if len(text) < 2 or _looks_like_cart_request(text):
            return
        session.customer_name = text
        session.step = ChatSession.Step.CUSTOMER_EMAIL
        session.save(update_fields=["customer_name", "step", "updated_at"])
        return

    if session.step == ChatSession.Step.CUSTOMER_EMAIL:
        email = text.strip().lower()
        if not EMAIL_RE.match(email):
            return
        session.customer_email = email
        session.step = ChatSession.Step.CUSTOMER_PHONE
        session.save(update_fields=["customer_email", "step", "updated_at"])
        return

    if session.step == ChatSession.Step.CUSTOMER_PHONE:
        if len(text) < 8:
            return
        session.customer_phone = text
        session.step = ChatSession.Step.CUSTOMER_ADDRESS
        session.save(update_fields=["customer_phone", "step", "updated_at"])
        return

    if session.step == ChatSession.Step.CUSTOMER_ADDRESS:
        if len(text) < 5:
            return
        session.customer_address = text
        session.step = ChatSession.Step.CONFIRM
        session.save(update_fields=["customer_address", "step", "updated_at"])


def _looks_like_cart_request(text: str) -> bool:
    low = text.lower()
    return any(
        k in low
        for k in ("panier", "cart", "voir mon panier", "vérifie le panier", "verifie le panier")
    )


def _should_block_action(action: dict | None, session: ChatSession, user_message: str) -> bool:
    if not action or not isinstance(action, dict):
        return False

    action_type = action.get("type")
    if not action_type:
        return False

    if action_type == "add_to_cart" and session.step in CUSTOMER_STEPS:
        return True

    if action_type == "add_to_cart":
        product_id = action.get("product_id")
        if product_id is not None and not _valid_product_id(product_id):
            return True
        if _is_affirmative_only(user_message) and not _message_has_quantity(user_message):
            return True
        if not _message_has_quantity(user_message) and not _quantity_in_recent_history(session_key):
            return True

    if action_type == "search_products":
        query = (action.get("product_query") or "").strip().lower()
        if query in GENERIC_SEARCH_TERMS:
            return True

    if action_type == "list_products" and not _explicit_catalog_request(user_message):
        return True

    if action_type == "list_products" and _wants_checkout(user_message):
        return True

    return False


def _quantity_in_recent_history(session_key: str) -> bool:
    """Vrai si le client a donné une quantité numérique récemment."""
    recent = (
        ChatMessage.objects.filter(session_key=session_key, role=ChatMessage.Role.USER)
        .order_by("-created_at")[:3]
    )
    return any(_message_has_quantity(m.content) for m in recent)


def _infer_continuation(text: str, session_key: str) -> dict | None:
    """Déduit une action uniquement quand le contexte est explicite — jamais de catalogue complet."""
    stripped = (text or "").strip()
    low = stripped.lower()
    prev = _plain(_last_assistant_text(session_key))

    if PHONE_RE.match(stripped):
        return None

    order_m = ORDER_RE.search(stripped.upper())
    if order_m and any(k in low for k in ("suivre", "suivi", "statut", "commande", "track")):
        return {"type": "track_order", "order_number": order_m.group(1).upper()}

    if low.isdigit() and any(
        k in prev for k in ("choix", "numéro", "numero", "lequel", "1.", "2.", "3.", "4.")
    ):
        if session_has_customer_phone_step(session_key):
            return None
        pid = int(low)
        if _valid_product_id(pid):
            return {"type": "add_to_cart", "product_id": pid, "quantity": 1}

    if _explicit_catalog_request(low):
        return {"type": "list_products", "limit": 10}

    if _looks_like_cart_request(low):
        return {"type": "view_cart"}

    return None


def session_has_customer_phone_step(session_key: str) -> bool:
    session = _get_chat_session(session_key)
    return session.step in {
        ChatSession.Step.CUSTOMER_PHONE,
        ChatSession.Step.CUSTOMER_ADDRESS,
        ChatSession.Step.CONFIRM,
    }


def _normalize_action(action: dict | None, session: ChatSession) -> dict | None:
    if not action or not isinstance(action, dict):
        return None
    action_type = action.get("type")
    if not action_type:
        return None

    normalized = {"type": action_type}
    for key in (
        "product_id",
        "product_query",
        "quantity",
        "limit",
        "order_number",
        "customer_name",
        "customer_email",
        "customer_phone",
        "customer_address",
    ):
        if key in action and action[key] not in (None, ""):
            normalized[key] = action[key]

    if action_type == "place_order":
        normalized.setdefault("customer_name", session.customer_name or "Client")
        normalized.setdefault("customer_email", session.customer_email or "client@afripul.tg")
        normalized.setdefault("customer_phone", session.customer_phone or "")
        normalized.setdefault("customer_address", session.customer_address or "")

    return normalized


def _parse_llm_response(content: str) -> dict:
    text = (content or "").strip()
    if not text:
        raise LLMServiceError("Réponse LLM vide.")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        reply_m = re.search(r'"reply"\s*:\s*"((?:[^"\\]|\\.)*)"', text, flags=re.S)
        if reply_m:
            reply = reply_m.group(1).encode().decode("unicode_escape")
            action_m = re.search(r'"action"\s*:\s*(\{[^}]*\}|null)', text, flags=re.S)
            action = None
            if action_m and action_m.group(1) != "null":
                try:
                    action = json.loads(action_m.group(1))
                except json.JSONDecodeError:
                    pass
            return {"reply": reply.strip(), "action": action}

    if text and not text.startswith("{"):
        return {"reply": text.replace("\n", "<br>"), "action": None}

    raise LLMServiceError("Réponse LLM invalide (JSON attendu).")


def _build_turn_context(history: list[ChatMessage]) -> str:
    if len(history) <= 1:
        return DEFAULT_TURN_CONTEXT

    lines = ["Tu as déjà conversé avec ce client. Ne répète pas la même réponse."]
    for msg in history[-6:-1]:
        who = "Client" if msg.role == ChatMessage.Role.USER else "Assistant"
        plain = re.sub(r"<[^>]+>", "", msg.content or "")[:180]
        lines.append(f"- {who} : {plain}")

    current = history[-1].content if history else ""
    plain_current = re.sub(r"<[^>]+>", "", current or "")
    return TURN_CONTEXT_TEMPLATE.format(
        context_lines="\n".join(lines),
        current_message=plain_current[:300],
    )


def _build_llm_messages(session_key: str, history: list[ChatMessage], session: ChatSession) -> list[dict]:
    system = SYSTEM_PROMPT_TEMPLATE.format(
        catalog=_build_catalog_text(),
        cart=_build_cart_text(session_key),
        checkout_state=_build_checkout_state(session),
        turn_context=_build_turn_context(history),
    )
    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    return messages


def _llm_unavailable_reply(exc: LLMServiceError) -> dict:
    from services.llm_config import llm_provider

    provider = llm_provider()
    if exc.code in ("429", "503"):
        reply = (
            "L'assistant est temporairement surchargé. "
            "Réessayez dans quelques instants."
        )
    elif provider == "gemini":
        reply = (
            f"L'assistant IA (Gemini) est indisponible. "
            f"Vérifiez GEMINI_API_KEY dans votre .env.<br>"
            f"<em>{exc}</em>"
        )
    else:
        reply = (
            f"L'assistant IA (Ollama) est indisponible. "
            f"Vérifiez qu'Ollama tourne ou passez en mode Gemini "
            f"(LLM_PROVIDER=gemini dans .env).<br>"
            f"<em>{exc}</em>"
        )
    return {
        "reply": reply,
        "intent": "llm_unavailable",
        "entities": {},
        "actions": [],
    }


def process_with_llm(*, message: str, session_key: str) -> dict:
    text = (message or "").strip()
    if not text:
        return {
            "reply": "Envoyez un message pour que je puisse vous aider.",
            "intent": "unknown",
            "entities": {},
            "actions": [],
        }

    if not llm_chat_enabled():
        return {
            "reply": "Le chat IA est désactivé (LLM_CHAT_ENABLED=false).",
            "intent": "disabled",
            "entities": {},
            "actions": [],
        }

    session = _get_chat_session(session_key)
    _save_message(session_key, ChatMessage.Role.USER, text)
    _sync_checkout_step(session, text)
    session.refresh_from_db()

    if _wants_modify_cart(text):
        result = _handle_modify_cart_request(session_key)
        _save_message(session_key, ChatMessage.Role.ASSISTANT, result["reply"])
        return result

    cart_update = _try_cart_modification(text, session_key)
    if cart_update:
        _save_message(session_key, ChatMessage.Role.ASSISTANT, cart_update["reply"])
        return cart_update

    history = _get_history(session_key)
    messages = _build_llm_messages(session_key, history, session)

    try:
        payload = llm_chat(messages=messages, model=llm_model())
        content = safe_extract_message_content(payload)
        parsed = _parse_llm_response(content)
    except LLMServiceError as exc:
        result = _llm_unavailable_reply(exc)
        _save_message(session_key, ChatMessage.Role.ASSISTANT, result["reply"])
        return result

    reply = (parsed.get("reply") or "").strip()
    action = _normalize_action(parsed.get("action"), session)

    if not action:
        action = _infer_continuation(text, session_key)
        if action:
            action = _normalize_action(action, session)

    if _should_block_action(action, session, text):
        action = None

    intent = "chat"
    actions: list = []

    if action and action.get("type"):
        result = execute_action(action, session_key=session_key)
        intent = result.intent
        actions = result.actions
        if result.success:
            if not reply or action.get("type") in ("place_order", "list_products"):
                reply = result.reply
            elif action.get("type") == "view_cart" and _wants_modify_cart(text):
                pass
        elif action.get("type") == "search_products" and reply:
            pass
        elif action.get("type") == "add_to_cart" and _is_affirmative_only(text):
            reply = (
                f"{reply}<br><br>Combien souhaitez-vous en commander ?"
                if reply
                else "Combien souhaitez-vous en commander ?"
            )
        elif reply:
            reply = f"{reply}<br><br>{result.reply}"
        else:
            reply = result.reply

        if action.get("type") == "place_order" and result.success:
            session.reset()

    if not reply:
        reply = "Je suis là pour vous aider. Que souhaitez-vous faire ?"

    _save_message(session_key, ChatMessage.Role.ASSISTANT, reply)
    return {
        "reply": reply,
        "intent": intent,
        "entities": {},
        "actions": actions,
    }
