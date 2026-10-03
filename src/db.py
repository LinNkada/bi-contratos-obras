"""Funções de conexão com o banco de dados."""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from src.config import Settings, load_settings

logger = logging.getLogger(__name__)

MIN_MYSQL_MAJOR_VERSION = 8


def get_engine(settings: Settings | None = None) -> Engine:
    """Cria a conexão com o MySQL a partir das configurações do .env."""
    settings = settings or load_settings()
    # URL.create monta a conexão sem quebrar se a senha tiver caracteres especiais.
    url = URL.create(
        drivername="mysql+pymysql",
        username=settings.mysql_user,
        password=settings.mysql_password,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def check_connection() -> None:
    """Testa a conexão e confirma que a versão do MySQL é suficiente."""
    engine = get_engine()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar_one()
        database = conn.execute(text("SELECT DATABASE()")).scalar_one()

    major = int(str(version).split(".")[0])
    if major < MIN_MYSQL_MAJOR_VERSION:
        raise RuntimeError(f"MySQL {MIN_MYSQL_MAJOR_VERSION}+ required, found {version}")
    logger.info("Connected to MySQL %s, database '%s'", version, database)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    check_connection()