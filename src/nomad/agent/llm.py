from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_llm_client(cfg: dict[str, Any], env: Any) -> tuple[Any, str, str] | None:
    """Devuelve (client, model, provider_name) para el primer proveedor disponible."""

    agent_cfg = cfg.get("agent") or {}
    provider = (agent_cfg.get("provider") or "auto").lower()
    model_override = agent_cfg.get("model")

    candidates = [
        # (provider_name, api_key, base_url, default_model, env_var_name)
        ("groq", env.groq_api_key, "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
        ("deepseek", env.deepseek_api_key, "https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
        ("openai", env.openai_api_key, None, "gpt-4o-mini", "OPENAI_API_KEY"),
    ]

    if provider != "auto":
        candidates = [c for c in candidates if c[0] == provider]

    for prov_name, api_key, base_url, default_model, env_var in candidates:
        if not api_key:
            continue
        model = model_override or default_model
        try:
            from openai import OpenAI

            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url

            client = OpenAI(**kwargs)
            logger.info("LLM: %s (%s)", prov_name, model)
            return client, model, prov_name
        except Exception as exc:
            logger.warning("LLM %s init error: %s", prov_name, exc)

    logger.info("Sin credenciales LLM validas: se usa modo heuristico local")
    return None
