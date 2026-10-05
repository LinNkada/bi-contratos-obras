"""Carga: grava no MySQL os dados validados e o histórico de qualidade."""
from __future__ import annotations

import logging
from datetime import date, datetime

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)

# Substituição: apaga quem tem chave estrangeira antes e grava os pais antes dos filhos.
DELETE_ORDER = (
    "dim_contrato", "dim_obra", "dim_cliente", "dim_calendario",
    "stg_contrato", "stg_obra", "stg_cliente",
    "ref_parametro", "ref_cidade",
)
INSERT_ORDER = (
    "ref_cidade", "ref_parametro",
    "stg_cliente", "stg_obra", "stg_contrato",
    "dim_calendario", "dim_cliente", "dim_obra", "dim_contrato",
)


def _to_python(value):
    """Converte valores do pandas/NumPy em tipos nativos do Python (ausentes viram None)."""
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.generic):
        return value.item()
    return value


def to_records(df: pd.DataFrame) -> list[dict]:
    columns = list(df.columns)
    return [
        {column: _to_python(value) for column, value in zip(columns, row)}
        for row in df.itertuples(index=False, name=None)
    ]


def insert_rows(conn: Connection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    columns = list(df.columns)
    names = ", ".join(columns)
    binds = ", ".join(f":{column}" for column in columns)
    conn.execute(text(f"INSERT INTO {table} ({names}) VALUES ({binds})"), to_records(df))
    logger.info("Loaded %s: %d rows", table, len(df))


def start_execution(engine: Engine, source: str, reference_date: date) -> int:
    """Registra o início da execução e confirma na hora, para o registro sobreviver a falhas."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO dq_execucao (iniciada_em, origem, data_referencia, status) "
                "VALUES (:started_at, :source, :reference_date, 'em_andamento')"
            ),
            {
                "started_at": datetime.now().replace(microsecond=0),
                "source": source,
                "reference_date": reference_date,
            },
        )
        return int(result.lastrowid)


def _finish_execution(conn: Connection, execution_id: int, status: str, message: str | None) -> None:
    conn.execute(
        text(
            "UPDATE dq_execucao SET finalizada_em = :finished_at, status = :status, "
            "mensagem = :message WHERE id_execucao = :execution_id"
        ),
        {
            "finished_at": datetime.now().replace(microsecond=0),
            "status": status,
            "message": message,
            "execution_id": execution_id,
        },
    )


def fail_execution(engine: Engine, execution_id: int, error: Exception) -> None:
    message = f"{type(error).__name__}: {error}"[:500]
    with engine.begin() as conn:
        _finish_execution(conn, execution_id, "falhou", message)


def load_all(
    engine: Engine,
    execution_id: int,
    frames: dict[str, pd.DataFrame],
    summary: pd.DataFrame,
    problems: pd.DataFrame,
) -> None:
    """Substitui staging, referência e dimensões e acrescenta o histórico, tudo em uma transação."""
    with engine.begin() as conn:
        for table in DELETE_ORDER:
            conn.exec_driver_sql(f"DELETE FROM {table}")
        for table in INSERT_ORDER:
            insert_rows(conn, table, frames[table])
        insert_rows(conn, "dq_resumo", summary)
        insert_rows(conn, "dq_problema", problems)
        _finish_execution(conn, execution_id, "concluida", None)