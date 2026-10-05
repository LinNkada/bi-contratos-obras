import re
from datetime import date, datetime

import pandas as pd

from src.etl.extract import extract_all, read_cities
from src.etl.load import to_records
from src.etl.schema import ddl_files, split_statements
from src.etl.transform import (
    build_calendar,
    build_frames,
    calendar_bounds,
    dim_obra_frame,
    issues_frame,
    staging_frame,
    summary_frame,
)
from src.etl.validate import validate_all
from src.synthetic.inject_errors import DIRTY_DIR

REF = date(2026, 9, 30)
EXPECTED_TABLES = {
    "ref_cidade", "ref_parametro", "stg_cliente", "stg_obra", "stg_contrato",
    "dim_calendario", "dim_cliente", "dim_obra", "dim_contrato",
}


def _clean_frames():
    sources = extract_all()
    cities = read_cities()
    result = validate_all(sources, cities, REF)
    frames = build_frames(sources, result, cities, 1, REF, datetime(2026, 10, 4, 20, 0, 0))
    return sources, result, frames


def test_to_records_converts_missing_and_numpy_values():
    df = pd.DataFrame(
        {
            "texto": ["a", None],
            "numero": [5, 7],
            "decimal": [1.5, float("nan")],
            "data": [date(2026, 9, 30), pd.NaT],
            "momento": [pd.Timestamp("2026-10-04 20:30:00"), pd.Timestamp("2026-10-04 20:31:00")],
        }
    )
    first, second = to_records(df)
    assert first["texto"] == "a"
    assert first["numero"] == 5 and isinstance(first["numero"], int)
    assert first["decimal"] == 1.5
    assert first["data"] == date(2026, 9, 30)
    assert first["momento"] == datetime(2026, 10, 4, 20, 30)
    assert second["texto"] is None
    assert second["decimal"] is None
    assert second["data"] is None


def test_calendar_has_one_row_per_day_with_portuguese_names():
    calendar = build_calendar(date(2026, 9, 28), date(2026, 10, 4))
    assert len(calendar) == 7
    assert calendar["data"].is_unique
    row = calendar[calendar["data"] == date(2026, 9, 30)].iloc[0]
    assert row["ano"] == 2026 and row["mes"] == 9 and row["trimestre"] == 3
    assert row["nome_mes"] == "Setembro"
    assert row["ano_mes"] == "2026-09"
    assert row["primeiro_dia_mes"] == date(2026, 9, 1)
    assert row["ultimo_dia_mes"] == date(2026, 9, 30)
    assert row["dia_semana"] == 3
    assert row["nome_dia_semana"] == "Quarta-feira"


def test_calendar_bounds_cover_the_data_and_the_following_year():
    clientes = pd.DataFrame({"data_cadastro": pd.to_datetime(["2024-01-10"])})
    contratos = pd.DataFrame(
        {
            "data_inicio": pd.to_datetime(["2024-03-01"]),
            "data_fim_prevista_inicial": pd.to_datetime(["2025-03-01"]),
            "data_fim_atual": pd.to_datetime(["2028-02-01"]),
            "data_retirada": pd.to_datetime([None]),
        }
    )
    assert calendar_bounds(clientes, contratos, REF) == (date(2024, 1, 1), date(2028, 12, 31))

    contratos["data_fim_atual"] = pd.to_datetime(["2026-01-01"])
    assert calendar_bounds(clientes, contratos, REF) == (date(2024, 1, 1), date(2027, 12, 31))


def test_staging_frame_keeps_text_and_adds_line_and_execution():
    source = pd.DataFrame(
        {
            "id_cliente": ["CLI-0001", ""],
            "nome_cliente": ["A", "B"],
            "data_cadastro": ["2024-01-10", "x"],
        }
    )
    frame = staging_frame(source, 7, datetime(2026, 10, 4, 20, 0, 0))
    assert list(frame["linha"]) == [2, 3]
    assert list(frame["id_execucao"]) == [7, 7]
    assert frame.loc[1, "id_cliente"] == ""
    assert (frame["carregado_em"] == pd.Timestamp("2026-10-04 20:00:00")).all()


def test_dim_obra_frame_adds_macro_region_or_none():
    valid = pd.DataFrame(
        {
            "id_obra": ["OBR-1", "OBR-2"],
            "id_cliente": ["CLI-1", "CLI-1"],
            "nome_obra": ["A", "B"],
            "cidade": ["São Paulo", "Cidade Nova"],
            "estado": ["SP", "SP"],
            "latitude": [-23.5, -23.6],
            "longitude": [-46.6, -46.7],
            "qtd_portas": [10, 20],
        }
    )
    cities = pd.DataFrame(
        {
            "cidade": ["São Paulo"],
            "estado": ["SP"],
            "macro_regiao": ["Sudeste"],
            "latitude": [-23.5505],
            "longitude": [-46.6333],
        }
    )
    frame = dim_obra_frame(valid, cities)
    assert frame.loc[0, "macro_regiao"] == "Sudeste"
    assert pd.isna(frame.loc[1, "macro_regiao"])


def test_build_frames_match_validation_counts():
    sources, result, frames = _clean_frames()
    assert set(frames) == EXPECTED_TABLES
    assert len(frames["dim_cliente"]) == len(result.clientes.valid)
    assert len(frames["dim_obra"]) == len(result.obras.valid)
    assert len(frames["dim_contrato"]) == len(result.contratos.valid)
    assert len(frames["stg_contrato"]) == result.contratos.received

    days = pd.to_datetime(frames["dim_calendario"]["data"])
    assert days.is_unique and days.is_monotonic_increasing
    assert (days.diff().dropna() == pd.Timedelta(days=1)).all()
    contratos = result.contratos.valid
    assert days.min() <= contratos["data_inicio"].min()
    assert days.max() >= contratos["data_fim_atual"].max()


def test_frame_columns_exist_in_the_ddl_and_are_not_generated():
    sources, result, frames = _clean_frames()
    frames = {
        **frames,
        "dq_resumo": summary_frame(result.summary, 1),
        "dq_problema": issues_frame(result.issues, 1),
    }
    statements = {}
    for path in ddl_files():
        for statement in split_statements(path.read_text(encoding="utf-8")):
            name = re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", statement).group(1)
            statements[name] = statement

    for table, frame in frames.items():
        for column in frame.columns:
            definition = re.search(rf"^\s*{column}\s[^\n]*", statements[table], re.MULTILINE)
            assert definition, f"{table}.{column} não existe no DDL"
            assert "GENERATED" not in definition.group(0), f"{table}.{column} é calculada pelo banco"


def test_summary_and_issue_frames_use_database_column_names():
    sources = extract_all(DIRTY_DIR)
    result = validate_all(sources, read_cities(), REF)

    summary = summary_frame(result.summary, 3)
    assert list(summary.columns) == [
        "id_execucao", "tabela", "registros_recebidos", "registros_validos",
        "registros_rejeitados", "registros_com_alerta",
    ]
    issues = issues_frame(result.issues, 3)
    assert list(issues.columns) == [
        "id_execucao", "tabela", "linha", "id_registro", "regra", "severidade", "detalhe",
    ]
    assert len(issues) == len(result.issues) > 0
    assert (issues["id_execucao"] == 3).all()