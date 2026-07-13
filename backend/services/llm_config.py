"""Configuration centralisée des fournisseurs LLM (local Ollama / API externe)."""

import os


class LLMServiceError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def llm_provider() -> str:
    """gemini si LLM_PROVIDER ou GEMINI_API_KEY est défini, sinon ollama."""
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if gemini_api_key():
        return "gemini"
    return "ollama"


def llm_chat_enabled() -> bool:
    return os.getenv("LLM_CHAT_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def llm_model() -> str:
    if llm_provider() == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
    return os.getenv("OLLAMA_MODEL", "qwen3:4b").strip()


def gemini_models() -> list[str]:
    primary = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
    fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
    models = [primary] if primary else []
    if fallbacks:
        for m in fallbacks.split(","):
            m = m.strip()
            if m and m not in models:
                models.append(m)
    return models or ["gemini-2.0-flash"]


def gemini_retry_count() -> int:
    try:
        return max(1, int(os.getenv("GEMINI_RETRY_COUNT", "3")))
    except ValueError:
        return 3


def gemini_retry_delay() -> float:
    try:
        return max(0.5, float(os.getenv("GEMINI_RETRY_DELAY", "2")))
    except ValueError:
        return 2.0


def llm_timeout() -> int:
    if llm_provider() == "gemini":
        try:
            return int(os.getenv("GEMINI_TIMEOUT", "180"))
        except ValueError:
            return 180
    try:
        return int(os.getenv("OLLAMA_TIMEOUT", "180"))
    except ValueError:
        return 180


def llm_json_format_enabled() -> bool:
    if llm_provider() == "gemini":
        return os.getenv("GEMINI_JSON_FORMAT", "true").strip().lower() in ("1", "true", "yes", "on")
    return os.getenv("OLLAMA_JSON_FORMAT", "true").strip().lower() in ("1", "true", "yes", "on")


def llm_max_history() -> int:
    try:
        return max(4, int(os.getenv("LLM_MAX_HISTORY", "32")))
    except ValueError:
        return 32


def gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def gemini_base_url() -> str:
    return os.getenv(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    ).rstrip("/")


def gemini_temperature() -> float:
    try:
        return float(os.getenv("GEMINI_TEMPERATURE", "0.2"))
    except ValueError:
        return 0.2


def gemini_max_output_tokens() -> int:
    try:
        return int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "2048"))
    except ValueError:
        return 2048


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
