import os
from datetime import date

import pytest
from sqlalchemy import text

from src.db import get_engine
from src.etl.extract import extract_all, read_cities
from src.etl.validate import validate_all
from src.pipeline import run_pipeline
from src.synthetic.inject_errors import DIRTY_DIR

requires_db = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="defina RUN_DB_TESTS=1 para testar contra o MySQL",
)

REF = date(2026, 9, 30)
COUNTED = (
    "ref_cidade", "ref_parametro", "stg_cliente", "stg_obra", "stg_contrato",
    "dim_calendario", "dim_cliente", "dim_obra", "dim_contrato",
)
CHECKSUMMED = ("ref_cidade", "ref_parametro", "dim_calendario", "dim_cliente", "dim_obra", "dim_contrato")


def snapshot(engine) -> dict:
    with engine.connect() as conn:
        counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in COUNTED}
        rows = conn.exec_driver_sql("CHECKSUM TABLE " + ", ".join(CHECKSUMMED)).fetchall()
        checksums = {row[0].split(".")[-1]: row[1] for row in rows}
        executions = conn.execute(text("SELECT COUNT(*) FROM dq_execucao")).scalar_one()
    return {"counts": counts, "checksums": checksums, "executions": executions}


@requires_db
def test_pipeline_is_idempotent():
    engine = get_engine()
    run_pipeline(report_dir=None)
    first = snapshot(engine)
    run_pipeline(report_dir=None)
    second = snapshot(engine)

    assert second["counts"] == first["counts"]
    assert second["checksums"] == first["checksums"]
    assert second["executions"] == first["executions"] + 1


@requires_db
def test_dimensions_match_the_valid_records():
    engine = get_engine()
    run_pipeline(report_dir=None)
    sources = extract_all()
    result = validate_all(sources, read_cities(), REF)
    counts = snapshot(engine)["counts"]

    assert counts["dim_cliente"] == len(result.clientes.valid)
    assert counts["dim_obra"] == len(result.obras.valid)
    assert counts["dim_contrato"] == len(result.contratos.valid)
    assert counts["stg_cliente"] == result.clientes.received
    assert counts["stg_obra"] == result.obras.received
    assert counts["stg_contrato"] == result.contratos.received


@requires_db
def test_dirty_source_loads_only_valid_records_and_records_the_problems():
    engine = get_engine()
    try:
        execution_id = run_pipeline(source=DIRTY_DIR, report_dir=None)
        result = validate_all(extract_all(DIRTY_DIR), read_cities(), REF)
        counts = snapshot(engine)["counts"]
        with engine.connect() as conn:
            problems = conn.execute(
                text("SELECT COUNT(*) FROM dq_problema WHERE id_execucao = :id"), {"id": execution_id}
            ).scalar_one()
            summaries = conn.execute(
                text("SELECT COUNT(*) FROM dq_resumo WHERE id_execucao = :id"), {"id": execution_id}
            ).scalar_one()

        assert counts["dim_contrato"] == len(result.contratos.valid)
        assert counts["dim_obra"] == len(result.obras.valid)
        assert counts["stg_contrato"] == result.contratos.received
        assert problems == len(result.issues) > 0
        assert summaries == 3
    finally:
        run_pipeline(report_dir=None)  # deixa a base limpa carregada


@requires_db
def test_failed_run_is_recorded_and_leaves_data_untouched(tmp_path):
    engine = get_engine()
    run_pipeline(report_dir=None)
    before = snapshot(engine)

    with pytest.raises(FileNotFoundError):
        run_pipeline(source=tmp_path / "nao_existe", report_dir=None)

    after = snapshot(engine)
    assert after["counts"] == before["counts"]
    assert after["checksums"] == before["checksums"]
    with engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM dq_execucao ORDER BY id_execucao DESC LIMIT 1")
        ).scalar_one()
    assert status == "falhou"