"""Indicadores de vencimento, risco e prazo, em duas implementações independentes.

O lado SQL lê as views (vw_vencimento e vw_contrato). O lado pandas recalcula tudo a
partir dos contratos válidos. A conferência compara os dois (ver reconcile.py).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

BANDS = {"0-30": (0, 30), "31-60": (31, 60), "61-90": (61, 90)}

EXPIRY_TOLERANCES = {
    "vencidos_em_aberto_valor": 0.005,
    "receita_a_vencer_0_30": 0.005,
    "receita_a_vencer_31_60": 0.005,
    "receita_a_vencer_61_90": 0.005,
    "receita_em_risco_0_30": 0.005,
    "receita_em_risco_31_60": 0.005,
    "receita_em_risco_61_90": 0.005,
    "receita_a_vencer_esperada_90": 0.05,
    "taxa_prorrogacao": 0.0002,
    "taxa_prorrogacao_encerrados": 0.0002,
    "desvio_prazo_medio_dias": 0.011,
    "duracao_prevista_media_dias": 0.011,
    "duracao_real_media_dias": 0.011,
}

_RESOLVED_SQL = (
    "data_fim_prevista_inicial <= data_referencia OR data_retirada IS NOT NULL OR prorrogado = 1"
)


def _number(value) -> float:
    """Valores nulos (por exemplo, divisão por zero no SQL) viram 0."""
    return 0.0 if value is None else float(value)


def _has_continuity(active: pd.DataFrame, reference: pd.Timestamp) -> pd.Series:
    """O cliente tem outro contrato ativo cujo prazo vai além do deste e da data de referência?"""
    flags = []
    for row in active.itertuples(index=False):
        limit = max(row.data_fim_atual, reference)
        others = active[
            (active["id_cliente"] == row.id_cliente) & (active["id_contrato"] != row.id_contrato)
        ]
        flags.append(bool((others["data_fim_atual"] > limit).any()))
    return pd.Series(flags, index=active.index, dtype=bool)


def expiry_indicators_from_pandas(
    obras: pd.DataFrame, contratos: pd.DataFrame, reference_date: date
) -> dict[str, float]:
    reference = pd.Timestamp(reference_date)
    extended = contratos["data_fim_atual"] > contratos["data_fim_prevista_inicial"]
    ended = contratos["data_retirada"].notna()

    active = contratos[~ended].merge(obras[["id_obra", "id_cliente"]], on="id_obra")
    days = (active["data_fim_atual"] - reference).dt.days
    overdue = active["data_fim_atual"] < reference
    continuity = _has_continuity(active, reference)

    kpis: dict[str, float] = {
        "vencidos_em_aberto_valor": round(float(active.loc[overdue, "valor_mensal"].sum()), 2)
    }
    expiring_total = 0.0
    for band, (low, high) in BANDS.items():
        key = band.replace("-", "_")
        in_band = ~overdue & (days >= low) & (days <= high)
        value = float(active.loc[in_band, "valor_mensal"].sum())
        at_risk = float(active.loc[in_band & ~continuity, "valor_mensal"].sum())
        kpis[f"receita_a_vencer_{key}"] = round(value, 2)
        kpis[f"receita_em_risco_{key}"] = round(at_risk, 2)
        expiring_total += value

    resolved = (contratos["data_fim_prevista_inicial"] <= reference) | ended | extended
    rate = float(extended[resolved].sum()) / resolved.sum() if resolved.sum() else 0.0
    rate_ended = float(extended[ended].sum()) / ended.sum() if ended.sum() else 0.0
    kpis["taxa_prorrogacao"] = round(rate, 4)
    kpis["taxa_prorrogacao_encerrados"] = round(rate_ended, 4)
    kpis["receita_a_vencer_esperada_90"] = round(expiring_total * (1 - rate), 2)

    planned = (contratos["data_fim_prevista_inicial"] - contratos["data_inicio"]).dt.days
    real = (contratos["data_retirada"] - contratos["data_inicio"]).dt.days
    deviation = (contratos["data_retirada"] - contratos["data_fim_prevista_inicial"]).dt.days
    kpis["desvio_prazo_medio_dias"] = round(float(deviation[ended].mean()), 2) if ended.any() else 0.0
    kpis["duracao_prevista_media_dias"] = round(float(planned.mean()), 2) if len(planned) else 0.0
    kpis["duracao_real_media_dias"] = round(float(real[ended].mean()), 2) if ended.any() else 0.0
    return kpis

def expiry_indicators_from_sql(engine: Engine) -> dict[str, float]:
    with engine.connect() as conn:
        bands = conn.execute(
            text(
                "SELECT faixa_vencimento, COALESCE(SUM(valor_mensal), 0), "
                "COALESCE(SUM(CASE WHEN em_risco = 1 THEN valor_mensal ELSE 0 END), 0) "
                "FROM vw_vencimento GROUP BY faixa_vencimento"
            )
        ).fetchall()
        totals = conn.execute(
            text(
                f"SELECT "
                f"SUM(CASE WHEN {_RESOLVED_SQL} THEN prorrogado END), "
                f"COUNT(CASE WHEN {_RESOLVED_SQL} THEN 1 END), "
                f"SUM(CASE WHEN status_contrato = 'encerrado' THEN prorrogado END), "
                f"COUNT(CASE WHEN status_contrato = 'encerrado' THEN 1 END), "
                f"AVG(CASE WHEN status_contrato = 'encerrado' THEN desvio_prazo_dias END), "
                f"AVG(duracao_prevista_dias), "
                f"AVG(CASE WHEN status_contrato = 'encerrado' THEN duracao_real_dias END) "
                f"FROM vw_contrato"
            )
        ).one()

    kpis: dict[str, float] = {"vencidos_em_aberto_valor": 0.0}
    for band in BANDS:
        key = band.replace("-", "_")
        kpis[f"receita_a_vencer_{key}"] = 0.0
        kpis[f"receita_em_risco_{key}"] = 0.0
    expiring_total = 0.0
    for band, value, at_risk in bands:
        if band == "vencido_em_aberto":
            kpis["vencidos_em_aberto_valor"] = round(float(value), 2)
        elif band in BANDS:
            key = band.replace("-", "_")
            kpis[f"receita_a_vencer_{key}"] = round(float(value), 2)
            kpis[f"receita_em_risco_{key}"] = round(float(at_risk), 2)
            expiring_total += float(value)

    # O MySQL divide DECIMAL com só 4 casas: a razão é calculada aqui, sem perder precisão.
    resolved_extended, resolved_total = _number(totals[0]), _number(totals[1])
    ended_extended, ended_total = _number(totals[2]), _number(totals[3])
    rate = resolved_extended / resolved_total if resolved_total else 0.0
    rate_ended = ended_extended / ended_total if ended_total else 0.0

    kpis["taxa_prorrogacao"] = round(rate, 4)
    kpis["taxa_prorrogacao_encerrados"] = round(rate_ended, 4)
    kpis["receita_a_vencer_esperada_90"] = round(expiring_total * (1 - rate), 2)
    kpis["desvio_prazo_medio_dias"] = round(_number(totals[4]), 2)
    kpis["duracao_prevista_media_dias"] = round(_number(totals[5]), 2)
    kpis["duracao_real_media_dias"] = round(_number(totals[6]), 2)
    return kpis