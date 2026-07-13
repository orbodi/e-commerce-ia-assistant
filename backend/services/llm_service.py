"""Point d'entrée unique pour les appels LLM (Ollama local ou Gemini API)."""

import json
import socket
import urllib.error
import urllib.request

from services.gemini_service import gemini_chat
from services.llm_config import LLMServiceError, llm_json_format_enabled, llm_provider, llm_timeout, ollama_base_url


def safe_extract_message_content(payload: dict) -> str:
    """Extrait le texte de la réponse, compatible Ollama et Gemini."""
    if not isinstance(payload, dict):
        return str(payload)

    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content", "")
        if content:
            return str(content).strip()

    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
        if texts:
            return "\n".join(texts).strip()

    return ""


def _ollama_chat(*, messages: list[dict], model: str) -> dict:
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if llm_json_format_enabled():
        body["format"] = "json"

    url = f"{ollama_base_url()}/api/chat"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=llm_timeout()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMServiceError(f"Ollama HTTP {exc.code}: {detail[:300]}", code=str(exc.code)) from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise LLMServiceError(f"Ollama indisponible: {exc}", code="unavailable") from exc


def llm_chat(*, messages: list[dict], model: str) -> dict:
    provider = llm_provider()
    if provider == "gemini":
        return gemini_chat(messages=messages, model=model)
    if provider == "ollama":
        return _ollama_chat(messages=messages, model=model)
    raise LLMServiceError(f"Fournisseur LLM inconnu: {provider}", code="config")
