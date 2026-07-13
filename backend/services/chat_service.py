from services.llm_chat_service import process_with_llm
from services.llm_config import llm_chat_enabled


def process_chat_message(*, message: str, session_key: str) -> dict:
    """Orchestrateur principal du chat — délègue au moteur LLM."""
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
            "reply": "Le chat IA est désactivé. Contactez-nous par WhatsApp.",
            "intent": "disabled",
            "entities": {},
            "actions": [],
        }

    return process_with_llm(message=text, session_key=session_key)
