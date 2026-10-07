"""Indicadores mensais (receita, carteira, movimentação e churn), em duas implementações.

O lado SQL lê vw_kpi_mensal. O lado pandas recalcula a partir das linhas contrato-mês.
As linhas de diferença usam o contrato "TOTAL", para entrarem no mesmo relatório.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

COUNT_COLUMNS = ("ativos_inicio", "novos", "retirados", "perdidos", "ativos_fim")
MONEY_COLUMNS = ("receita", "carteira_inicio", "carteira_fim", "valor_perdido")
RATE_COLUMNS = (
    "churn_contratual_mes", "churn_financeiro_mes",
    "churn_contratual_12m", "churn_financeiro_12m",
)
ALL_COLUMNS = COUNT_COLUMNS + MONEY_COLUMNS + RATE_COLUMNS
TOLERANCES = {
    **{column: 0.0 for column in COUNT_COLUMNS},
    **{column: 0.05 for column in MONEY_COLUMNS},
    **{column: 0.00002 for column in RATE_COLUMNS},
}
DIFFERENCE_COLUMNS = ["id_contrato", "mes", "coluna", "pandas", "sql"]


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Razão com 6 casas. Denominador zero (ou janela incompleta) vira vazio."""
    return (numerator / denominator.where(denominator != 0)).round(6)


def monthly_kpis_from_pandas(monthly: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """Mesmas colunas de vw_kpi_mensal, a partir das linhas contrato-mês."""
    if monthly.empty:
        return pd.DataFrame(columns=list(ALL_COLUMNS))
    grouped = monthly.groupby("mes").agg(
        receita=("receita_mes", "sum"),
        ativos_inicio=("ativo_no_inicio_mes", "sum"),
        novos=("iniciou_no_mes", "sum"),
        retirados=("retirado_no_mes", "sum"),
        perdidos=("perdido_no_mes", "sum"),
        ativos_fim=("ativo_no_fim_mes", "sum"),
        carteira_inicio=("carteira_inicio_mes", "sum"),
        carteira_fim=("carteira_fim_mes", "sum"),
        valor_perdido=("valor_perdido_mes", "sum"),
    )
    last_month = pd.Timestamp(reference_date).to_period("M").to_timestamp()
    months = pd.date_range(grouped.index.min(), last_month, freq="MS")
    frame = grouped.reindex(months, fill_value=0).astype(float)  # meses sem contrato ficam zerados
    frame.index.name = "mes"

    sums = frame.rolling(12, min_periods=12).sum()  # vazio até haver 12 meses completos
    frame["churn_contratual_mes"] = _ratio(frame["perdidos"], frame["ativos_inicio"])
    frame["churn_financeiro_mes"] = _ratio(frame["valor_perdido"], frame["carteira_inicio"])
    frame["churn_contratual_12m"] = _ratio(sums["perdidos"], sums["ativos_inicio"])
    frame["churn_financeiro_12m"] = _ratio(sums["valor_perdido"], sums["carteira_inicio"])
    return frame


def monthly_kpis_from_sql(engine: Engine) -> pd.DataFrame:
    columns = ", ".join(("mes",) + ALL_COLUMNS)
    with engine.connect() as conn:
        frame = pd.read_sql_query(text(f"SELECT {columns} FROM vw_kpi_mensal ORDER BY mes"), conn)
    frame["mes"] = pd.to_datetime(frame["mes"])
    for column in ALL_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return frame.set_index("mes")


def compare_monthly_kpis(expected: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Diferenças entre pandas (expected) e SQL (actual), mês a mês."""
    months = expected.index.union(actual.index)
    rows: list[dict] = []
    for column, tolerance in TOLERANCES.items():
        left = expected[column].reindex(months)
        right = actual[column].reindex(months)
        equal = (left - right).abs().le(tolerance) | (left.isna() & right.isna())
        for month in months[~equal.to_numpy()]:
            rows.append(
                {"id_contrato": "TOTAL", "mes": month, "coluna": column,
                 "pandas": left[month], "sql": right[month]}
            )
    return pd.DataFrame(rows, columns=DIFFERENCE_COLUMNS)


def latest_churn(frame: pd.DataFrame) -> dict[str, float]:
    """Churn em 12 meses móveis do último mês, como indicador de destaque."""
    keys = ("churn_contratual_12m", "churn_financeiro_12m")
    if frame.empty:
        return {key: 0.0 for key in keys}
    last = frame.iloc[-1]
    return {key: 0.0 if pd.isna(last[key]) else round(float(last[key]), 6) for key in keys}