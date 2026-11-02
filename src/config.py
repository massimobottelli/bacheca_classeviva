"""Caricamento della configurazione da file .env.

Mantiene le dipendenze a zero: il parsing di .env è fatto a mano.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
ATTACHMENTS_DIR = DATA_DIR / "attachments"
DB_PATH = DATA_DIR / "state.db"
LOG_DIR = PROJECT_ROOT / "logs"


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Rimuovi virgolette opzionali
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


class ConfigError(RuntimeError):
    """Configurazione mancante o non valida."""


@dataclass(frozen=True)
class Config:
    # ClasseViva
    cv_uid: str
    cv_password: str
    cv_cid: str
    cv_pin: str
    mark_as_read: bool
    # Telegram
    tg_bot_token: str
    tg_chat_id: str
    # LLM
    llm_api_url: str
    llm_api_key: str
    llm_model: str
    # Comportamento
    backfill_days: int
    request_delay: float


def _get(file_values: dict[str, str], key: str, default: str = "") -> str:
    """Preferisci variabile d'ambiente, poi file .env, poi default."""
    return os.environ.get(key, file_values.get(key, default)).strip()


def _get_bool(file_values: dict[str, str], key: str, default: bool) -> bool:
    raw = _get(file_values, key, "")
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "si", "sì", "on")


def _normalize_llm_url(url: str) -> str:
    """Garantisce che l'URL LLM punti all'endpoint chat/completions.

    Accetta sia l'endpoint completo (…/v1/chat/completions) sia la sola
    base API (…/v1): in questo caso viene completato automaticamente.
    """
    url = url.strip()
    if url and not url.rstrip("/").endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


def load_config(env_file: Path = ENV_FILE) -> Config:
    values = _parse_env_file(env_file)

    cfg = Config(
        cv_uid=_get(values, "CV_UID"),
        cv_password=_get(values, "CV_PASSWORD"),
        cv_cid=_get(values, "CV_CID"),
        cv_pin=_get(values, "CV_PIN"),
        # Default FALSE: non segnare gli avvisi come letti
        mark_as_read=_get_bool(values, "MARK_AS_READ", False),
        tg_bot_token=_get(values, "TG_BOT_TOKEN"),
        tg_chat_id=_get(values, "TG_CHAT_ID"),
        llm_api_url=_normalize_llm_url(_get(values, "LLM_API_URL")),
        llm_api_key=_get(values, "LLM_API_KEY"),
        llm_model=_get(values, "LLM_MODEL"),
        backfill_days=int(_get(values, "BACKFILL_DAYS", "7") or "7"),
        request_delay=float(_get(values, "REQUEST_DELAY", "1") or "1"),
    )

    missing = []
    if not cfg.cv_uid:
        missing.append("CV_UID")
    if not cfg.cv_password:
        missing.append("CV_PASSWORD")
    if not cfg.tg_bot_token:
        missing.append("TG_BOT_TOKEN")
    if not cfg.tg_chat_id:
        missing.append("TG_CHAT_ID")
    if missing:
        raise ConfigError(
            "Campi obbligatori mancanti nel file .env: "
            + ", ".join(missing)
            + f"\nEsegui 'python3 scripts/setup_env.py' oppure copia .env.example in .env e compilalo."
        )
    return cfg


def ensure_dirs() -> None:
    """Crea le directory di lavoro se non esistono."""
    for directory in (DATA_DIR, ATTACHMENTS_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)