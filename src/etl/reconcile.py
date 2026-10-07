"""Conferência independente: recalcula em pandas o que as views do MySQL calculam.

O pandas expande cada contrato dia a dia (um caminho diferente do SQL, que usa
diferenças entre datas) e compara com as views mês a mês e nos indicadores gerais.

Uso (a partir da raiz do projeto, depois de rodar o pipeline):
    python -m src.etl.reconcile
    python -m src.etl.reconcile --source data/raw_sujo
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import PROJECT_ROOT
from src.db import get_engine
from src.etl.extract import extract_all, read_cities
from src.etl.indicators import (
    EXPIRY_TOLERANCES,
    expiry_indicators_from_pandas,
    expiry_indicators_from_sql,
)
from src.etl.quality import REPORTS_DIR
from src.etl.validate import validate_all

logger = logging.getLogger(__name__)

LOST_REASONS = ("cancelado_cliente", "rescindido")
KEY_COLUMNS = ["id_contrato", "mes"]
EXACT_COLUMNS = [
    "dias_ativos", "ativo_no_inicio_mes", "iniciou_no_mes",
    "retirado_no_mes", "perdido_no_mes", "ativo_no_fim_mes",
]
MONEY_COLUMNS = ["receita_mes", "carteira_inicio_mes", "carteira_fim_mes", "valor_perdido_mes"]
MONEY_TOLERANCE = 0.01  # o MySQL arredonda a divisão em 6 casas antes do ROUND
KPI_TOLERANCES = {"carteira_ativa": 0.005, "receita_total": 0.05, **EXPIRY_TOLERANCES}
DIFFERENCE_COLUMNS = ["id_contrato", "mes", "coluna", "pandas", "sql"]

# --------------------------------------------------------------------------
# Lado pandas
# --------------------------------------------------------------------------
def expand_active_days(contratos: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """Uma linha por contrato e por dia em que a proteção esteve instalada."""
    reference = pd.Timestamp(reference_date)
    frames = []
    for row in contratos.itertuples(index=False):
        last_day = row.data_retirada if pd.notna(row.data_retirada) else reference
        days = pd.date_range(row.data_inicio, last_day, freq="D")
        frames.append(
            pd.DataFrame(
                {"id_contrato": row.id_contrato, "valor_mensal": row.valor_mensal, "dia": days}
            )
        )
    if not frames:
        return pd.DataFrame(
            {
                "id_contrato": pd.Series(dtype=str),
                "valor_mensal": pd.Series(dtype=float),
                "dia": pd.Series(dtype="datetime64[ns]"),
            }
        )
    return pd.concat(frames, ignore_index=True)


def _round_half_up(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def monthly_from_pandas(contratos: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """Mesmas colunas de vw_contrato_mes, calculadas a partir dos dias ativos."""
    reference = pd.Timestamp(reference_date)
    days = expand_active_days(contratos, reference_date)
    days["mes"] = days["dia"].dt.to_period("M").dt.to_timestamp()
    days["dias_no_mes"] = days["dia"].dt.days_in_month
    grouped = days.groupby(KEY_COLUMNS, as_index=False).agg(
        valor_mensal=("valor_mensal", "first"),
        dias_ativos=("dia", "count"),
        dias_no_mes=("dias_no_mes", "first"),
    )
    grouped["receita_mes"] = [
        _round_half_up(Decimal(str(float(valor))) * int(dias) / int(no_mes))
        for valor, dias, no_mes in zip(
            grouped["valor_mensal"], grouped["dias_ativos"], grouped["dias_no_mes"]
        )
    ]

    info = contratos.set_index("id_contrato")[["data_inicio", "data_retirada", "motivo_encerramento"]]
    frame = grouped.join(info, on="id_contrato")
    period_end = (frame["mes"] + pd.offsets.MonthEnd(0)).clip(upper=reference)
    retired_in_month = (frame["data_retirada"] >= frame["mes"]) & (frame["data_retirada"] <= period_end)

    frame["ativo_no_inicio_mes"] = (frame["data_inicio"] < frame["mes"]).astype(int)
    frame["iniciou_no_mes"] = (
        (frame["data_inicio"] >= frame["mes"]) & (frame["data_inicio"] <= period_end)
    ).astype(int)
    frame["retirado_no_mes"] = retired_in_month.astype(int)
    frame["perdido_no_mes"] = (retired_in_month & frame["motivo_encerramento"].isin(LOST_REASONS)).astype(int)
    frame["ativo_no_fim_mes"] = (
        (frame["data_inicio"] <= period_end)
        & (frame["data_retirada"].isna() | (frame["data_retirada"] > period_end))
    ).astype(int)
    frame["carteira_inicio_mes"] = frame["valor_mensal"] * frame["ativo_no_inicio_mes"]
    frame["carteira_fim_mes"] = frame["valor_mensal"] * frame["ativo_no_fim_mes"]
    frame["valor_perdido_mes"] = frame["valor_mensal"] * frame["perdido_no_mes"]
    return frame[KEY_COLUMNS + EXACT_COLUMNS[:1] + ["receita_mes"] + EXACT_COLUMNS[1:] + MONEY_COLUMNS[1:]]


def monthly_totals(monthly: pd.DataFrame) -> pd.DataFrame:
    """Totais por mês, para leitura humana no relatório."""
    return monthly.groupby("mes", as_index=False).agg(
        receita=("receita_mes", "sum"),
        ativos_inicio=("ativo_no_inicio_mes", "sum"),
        novos=("iniciou_no_mes", "sum"),
        retirados=("retirado_no_mes", "sum"),
        perdidos=("perdido_no_mes", "sum"),
        ativos_fim=("ativo_no_fim_mes", "sum"),
        carteira_fim=("carteira_fim_mes", "sum"),
    )


def kpis_from_pandas(
    obras: pd.DataFrame, contratos: pd.DataFrame, monthly: pd.DataFrame, reference_date: date
) -> dict[str, float]:
    reference = pd.Timestamp(reference_date)
    active = contratos["data_retirada"].isna()
    active_works = set(contratos.loc[active, "id_obra"])
    works_with_contracts = set(contratos["id_obra"])

    is_active = obras["id_obra"].isin(active_works)
    has_no_contract = ~obras["id_obra"].isin(works_with_contracts)
    is_closed = ~is_active & ~has_no_contract
    return {
        "contratos_ativos": int(active.sum()),
        "contratos_encerrados": int((~active).sum()),
        "carteira_ativa": round(float(contratos.loc[active, "valor_mensal"].sum()), 2),
        "vencidos_em_aberto": int((active & (contratos["data_fim_atual"] < reference)).sum()),
        "obras_ativas": int(is_active.sum()),
        "obras_encerradas": int(is_closed.sum()),
        "obras_sem_contrato": int(has_no_contract.sum()),
        "portas_em_operacao": int(obras.loc[is_active, "qtd_portas"].sum()),
        "receita_total": round(float(monthly["receita_mes"].sum()), 2),
    }


# --------------------------------------------------------------------------
# Lado SQL
# --------------------------------------------------------------------------
def read_reference_date(engine: Engine) -> date:
    with engine.connect() as conn:
        value = conn.execute(
            text("SELECT valor FROM ref_parametro WHERE chave = 'data_referencia'")
        ).scalar_one_or_none()
    if value is None:
        raise RuntimeError("Reference date not found in ref_parametro: run python -m src.pipeline first")
    return date.fromisoformat(value)


def last_source(engine: Engine) -> Path:
    """Pasta dos CSVs lidos pela última execução concluída."""
    with engine.connect() as conn:
        origin = conn.execute(
            text("SELECT origem FROM dq_execucao WHERE status = 'concluida' ORDER BY id_execucao DESC LIMIT 1")
        ).scalar_one_or_none()
    if origin is None:
        raise RuntimeError("No successful execution found: run python -m src.pipeline first")
    return PROJECT_ROOT / origin


def monthly_from_sql(engine: Engine) -> pd.DataFrame:
    columns = ", ".join(KEY_COLUMNS + EXACT_COLUMNS + MONEY_COLUMNS)
    with engine.connect() as conn:
        frame = pd.read_sql_query(text(f"SELECT {columns} FROM vw_contrato_mes"), conn)
    frame["mes"] = pd.to_datetime(frame["mes"])
    for column in EXACT_COLUMNS:
        frame[column] = frame[column].astype(int)
    for column in MONEY_COLUMNS:
        frame[column] = frame[column].astype(float)
    return frame


def kpis_from_sql(engine: Engine) -> dict[str, float]:
    kpis: dict[str, float] = {
        "contratos_ativos": 0, "contratos_encerrados": 0, "carteira_ativa": 0.0,
        "vencidos_em_aberto": 0, "obras_ativas": 0, "obras_encerradas": 0,
        "obras_sem_contrato": 0, "portas_em_operacao": 0, "receita_total": 0.0,
    }
    with engine.connect() as conn:
        contract_rows = conn.execute(
            text(
                "SELECT status_contrato, COUNT(*), COALESCE(SUM(valor_mensal), 0), "
                "COALESCE(SUM(vencido_em_aberto), 0) FROM vw_contrato GROUP BY status_contrato"
            )
        ).fetchall()
        work_rows = conn.execute(
            text(
                "SELECT status_obra, COUNT(*), COALESCE(SUM(qtd_portas), 0) "
                "FROM vw_obra GROUP BY status_obra"
            )
        ).fetchall()
        revenue = conn.execute(text("SELECT COALESCE(SUM(receita_mes), 0) FROM vw_contrato_mes")).scalar_one()

    for status, count, value, overdue in contract_rows:
        if status == "ativo":
            kpis["contratos_ativos"] = int(count)
            kpis["carteira_ativa"] = round(float(value), 2)
            kpis["vencidos_em_aberto"] = int(overdue)
        elif status == "encerrado":
            kpis["contratos_encerrados"] = int(count)
    for status, count, doors in work_rows:
        if status == "ativa":
            kpis["obras_ativas"] = int(count)
            kpis["portas_em_operacao"] = int(doors)
        elif status == "encerrada":
            kpis["obras_encerradas"] = int(count)
        elif status == "sem_contrato":
            kpis["obras_sem_contrato"] = int(count)
    kpis["receita_total"] = round(float(revenue), 2)
    return kpis


# --------------------------------------------------------------------------
# Comparação e relatório
# --------------------------------------------------------------------------
def compare_monthly(expected: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Diferenças entre pandas (expected) e SQL (actual), contrato a contrato e mês a mês."""
    merged = expected.merge(
        actual, on=KEY_COLUMNS, how="outer", suffixes=("_pandas", "_sql"), indicator=True
    )
    rows: list[dict] = []

    def add(frame: pd.DataFrame, column: str, left: str, right: str) -> None:
        for contract, month, value_pandas, value_sql in frame[
            ["id_contrato", "mes", left, right]
        ].itertuples(index=False, name=None):
            rows.append(
                {"id_contrato": contract, "mes": month, "coluna": column,
                 "pandas": value_pandas, "sql": value_sql}
            )

    only_pandas = merged[merged["_merge"] == "left_only"].assign(p="presente", s="ausente")
    only_sql = merged[merged["_merge"] == "right_only"].assign(p="ausente", s="presente")
    add(only_pandas, "linha", "p", "s")
    add(only_sql, "linha", "p", "s")

    both = merged[merged["_merge"] == "both"]
    for column in EXACT_COLUMNS:
        left, right = f"{column}_pandas", f"{column}_sql"
        add(both[both[left] != both[right]], column, left, right)
    for column in MONEY_COLUMNS:
        left, right = f"{column}_pandas", f"{column}_sql"
        add(both[(both[left] - both[right]).abs() > MONEY_TOLERANCE], column, left, right)
    return pd.DataFrame(rows, columns=DIFFERENCE_COLUMNS)


def compare_kpis(expected: dict[str, float], actual: dict[str, float]) -> pd.DataFrame:
    rows = []
    for name, value in expected.items():
        other = actual[name]
        tolerance = KPI_TOLERANCES.get(name, 0.0)
        rows.append(
            {"indicador": name, "pandas": value, "sql": other, "ok": abs(value - other) <= tolerance}
        )
    return pd.DataFrame(rows)


def format_reconciliation(
    kpis: pd.DataFrame,
    totals: pd.DataFrame,
    differences: pd.DataFrame,
    source: str,
    reference_date: date,
) -> str:
    diverging = int((~kpis["ok"]).sum())
    if differences.empty and diverging == 0:
        verdict = "Nenhuma diferença encontrada."
    else:
        verdict = f"ATENÇÃO: {len(differences)} diferença(s) mensal(is) e {diverging} indicador(es) divergente(s)."
    lines = [
        "# Conferência SQL × pandas",
        "",
        f"- Origem: `{source}`",
        f"- Data de referência: {reference_date.isoformat()}",
        f"- Resultado: {verdict}",
        "",
        "## Indicadores",
        "",
        "| Indicador | pandas | SQL | Situação |",
        "|---|---:|---:|---|",
    ]
    for row in kpis.itertuples(index=False):
        lines.append(f"| {row.indicador} | {row.pandas} | {row.sql} | {'ok' if row.ok else 'DIVERGE'} |")
    lines += [
        "",
        "## Evolução mensal (pandas)",
        "",
        "| Mês | Receita | Ativos no início | Novos | Retirados | Perdidos | Ativos no fim | Carteira no fim |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in totals.itertuples(index=False):
        lines.append(
            f"| {row.mes:%Y-%m} | {row.receita:.2f} | {row.ativos_inicio} | {row.novos} | "
            f"{row.retirados} | {row.perdidos} | {row.ativos_fim} | {row.carteira_fim:.2f} |"
        )
    if not differences.empty:
        lines += ["", "## Diferenças (até 50)", "", "| Contrato | Mês | Coluna | pandas | SQL |", "|---|---|---|---:|---:|"]
        for row in differences.head(50).itertuples(index=False):
            lines.append(f"| {row.id_contrato} | {row.mes:%Y-%m} | {row.coluna} | {row.pandas} | {row.sql} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile the MySQL views with an independent pandas calculation.")
    parser.add_argument("--source", type=Path, default=None, help="CSV folder (default: the last successful run)")
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    engine = get_engine()
    reference_date = read_reference_date(engine)
    source = args.source or last_source(engine)

    result = validate_all(extract_all(source), read_cities(), reference_date)
    obras, contratos = result.obras.valid, result.contratos.valid
    monthly = monthly_from_pandas(contratos, reference_date)

    differences = compare_monthly(monthly, monthly_from_sql(engine))
    expected = {
        **kpis_from_pandas(obras, contratos, monthly, reference_date),
        **expiry_indicators_from_pandas(obras, contratos, reference_date),
    }
    actual = {**kpis_from_sql(engine), **expiry_indicators_from_sql(engine)}
    kpis = compare_kpis(expected, actual)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "conferencia_sql_pandas.md"
    report_path.write_text(
        format_reconciliation(kpis, monthly_totals(monthly), differences, str(source), reference_date),
        encoding="utf-8",
    )
    ok = differences.empty and bool(kpis["ok"].all())
    logger.info(
        "Monthly rows compared: %d | monthly differences: %d | diverging indicators: %d",
        len(monthly), len(differences), int((~kpis["ok"]).sum()),
    )
    logger.info("Report written to %s", report_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()