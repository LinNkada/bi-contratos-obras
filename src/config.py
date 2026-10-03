"""Configurações da aplicação, lidas das variáveis de ambiente (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    reference_date: date


def _require(name: str) -> str:
    """Lê uma variável obrigatória e falha cedo, com mensagem clara, se faltar."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_reference_date() -> date:
    """Data de referência do projeto (REFERENCE_DATE), sem exigir as credenciais do MySQL."""
    return date.fromisoformat(os.getenv("REFERENCE_DATE", "2026-09-30"))


def load_settings() -> Settings:
    return Settings(
        mysql_host=os.getenv("MYSQL_HOST", "localhost"),
        mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
        mysql_database=_require("MYSQL_DATABASE"),
        mysql_user=_require("MYSQL_USER"),
        mysql_password=_require("MYSQL_PASSWORD"),
        reference_date=get_reference_date(),
    )