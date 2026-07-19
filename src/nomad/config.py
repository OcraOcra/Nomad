from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "settings.yaml"


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    deepseek_api_key: str | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    bccr_email: str | None = Field(default=None, alias="BCCR_EMAIL")
    bccr_token: str | None = Field(default=None, alias="BCCR_TOKEN")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    class Config:
        env_file = ".env"
        extra = "ignore"


def load_yaml_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs(cfg: dict[str, Any]) -> dict[str, Path]:
    paths = cfg.get("paths", {})
    resolved: dict[str, Path] = {}
    for key, rel in paths.items():
        p = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        if key.endswith("_file"):
            p.parent.mkdir(parents=True, exist_ok=True)
        else:
            p.mkdir(parents=True, exist_ok=True)
        resolved[key] = p
    return resolved


def get_config(path: Path | None = None) -> tuple[dict[str, Any], Settings, dict[str, Path]]:
    cfg = load_yaml_config(path)
    env = Settings()
    paths = ensure_dirs(cfg)
    return cfg, env, paths
