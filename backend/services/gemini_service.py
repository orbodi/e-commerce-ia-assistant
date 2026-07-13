import json
import socket
import time
import urllib.error
import urllib.request

from services.llm_config import (
    LLMServiceError,
    gemini_api_key,
    gemini_base_url,
    gemini_max_output_tokens,
    gemini_models,
    gemini_retry_count,
    gemini_retry_delay,
    gemini_temperature,
    llm_json_format_enabled,
    llm_timeout,
)


def _convert_messages(messages: list[dict]) -> tuple[dict | None, list[dict]]:
    system_parts: list[str] = []
    contents: list[dict] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)

        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})
        else:
            contents.append({"role": "user", "parts": [{"text": content}]})

    system_instruction = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return system_instruction, contents


def _request_gemini(*, model: str, body: dict, timeout: int) -> dict:
    api_key = gemini_api_key()
    if not api_key:
        raise LLMServiceError("GEMINI_API_KEY manquante.", code="config")

    url = f"{gemini_base_url()}/models/{model}:generateContent?key={api_key}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise LLMServiceError(
            f"Gemini HTTP {exc.code}: {body_text[:300]}",
            code=str(exc.code),
        ) from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise LLMServiceError(f"Gemini indisponible: {exc}", code="unavailable") from exc


def gemini_chat(*, messages: list[dict], model: str | None = None) -> dict:
    """Appelle l'API Gemini avec repli sur d'autres modèles et retries sur 429/503."""
    models = gemini_models()
    if model and model not in models:
        models = [model] + models

    system_instruction, contents = _convert_messages(messages)
    if not contents:
        raise LLMServiceError("Aucun message utilisateur pour Gemini.", code="input")

    generation_config: dict = {
        "temperature": gemini_temperature(),
        "maxOutputTokens": gemini_max_output_tokens(),
    }
    if llm_json_format_enabled():
        generation_config["responseMimeType"] = "application/json"

    body: dict = {"contents": contents, "generationConfig": generation_config}
    if system_instruction:
        body["systemInstruction"] = system_instruction

    timeout = llm_timeout()
    retries = gemini_retry_count()
    delay = gemini_retry_delay()
    last_error: LLMServiceError | None = None

    for candidate in models:
        for attempt in range(retries):
            try:
                return _request_gemini(model=candidate, body=body, timeout=timeout)
            except LLMServiceError as exc:
                last_error = exc
                if exc.code in ("429", "503") and attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
                if exc.code in ("429", "503"):
                    break
                raise
        if last_error and last_error.code in ("429", "503"):
            continue

    if last_error:
        raise last_error
    raise LLMServiceError("Aucun modèle Gemini disponible.", code="unavailable")
