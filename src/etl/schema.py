"""Criação (e recriação) do esquema do banco a partir dos scripts em sql/.

Uso (a partir da raiz do projeto):
    python -m src.etl.schema            # cria o que faltar (pode repetir sem problema)
    python -m src.etl.schema --reset    # apaga TODAS as tabelas e views do projeto e recria
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from src.config import PROJECT_ROOT
from src.db import get_engine

logger = logging.getLogger(__name__)

DDL_DIR = PROJECT_ROOT / "sql" / "ddl"
VIEWS_DIR = PROJECT_ROOT / "sql" / "views"

# Ordem de remoção: quem tem chave estrangeira vem antes da tabela que referencia.
TABLES_DROP_ORDER = (
    "dim_contrato", "dim_obra", "dim_cliente", "dim_calendario",
    "stg_contrato", "stg_obra", "stg_cliente",
    "dq_problema", "dq_resumo", "dq_execucao",
    "ref_parametro", "ref_cidade",
)
VIEWS_DROP_ORDER = ("vw_contrato_mes", "vw_obra", "vw_contrato")


def split_statements(script: str) -> list[str]:
    """Separa um script SQL em comandos, ignorando comentários de linha (-- ...)."""
    lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def ddl_files(ddl_dir: Path = DDL_DIR) -> list[Path]:
    """Scripts de criação de tabelas, em ordem. O 00 (criação do banco) fica de fora."""
    return sorted(path for path in ddl_dir.glob("*.sql") if not path.name.startswith("00_"))


def view_files(views_dir: Path = VIEWS_DIR) -> list[Path]:
    return sorted(views_dir.glob("*.sql"))


def _run_scripts(engine: Engine, paths: list[Path]) -> None:
    with engine.begin() as conn:
        for path in paths:
            for statement in split_statements(path.read_text(encoding="utf-8")):
                conn.exec_driver_sql(statement)
            logger.info("Applied %s", path.name)


def apply_schema(engine: Engine, ddl_dir: Path = DDL_DIR) -> None:
    """Cria as tabelas que ainda não existem. Pode ser repetido sem efeito colateral."""
    _run_scripts(engine, ddl_files(ddl_dir))


def apply_views(engine: Engine, views_dir: Path = VIEWS_DIR) -> None:
    """Cria ou atualiza as views (CREATE OR REPLACE). As tabelas precisam existir."""
    _run_scripts(engine, view_files(views_dir))


def reset_schema(engine: Engine) -> None:
    """Apaga views e tabelas do projeto, inclusive os dados e o histórico de qualidade."""
    with engine.begin() as conn:
        for view in VIEWS_DROP_ORDER:
            conn.exec_driver_sql(f"DROP VIEW IF EXISTS {view}")
        for table in TABLES_DROP_ORDER:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
    logger.info("Dropped all project views and tables")


def list_tables(engine: Engine) -> list[str]:
    return sorted(inspect(engine).get_table_names())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or recreate the database schema.")
    parser.add_argument("--reset", action="store_true", help="drop all project tables and views first")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    engine = get_engine()
    if args.reset:
        reset_schema(engine)
    apply_schema(engine)
    apply_views(engine)
    logger.info("Tables: %s", ", ".join(list_tables(engine)))


if __name__ == "__main__":
    main()