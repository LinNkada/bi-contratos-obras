from datetime import date

import pandas as pd
import pytest

from src.etl.monthly_kpis import compare_monthly_kpis, monthly_kpis_from_pandas
from src.etl.reconcile import monthly_from_pandas

REF = date(2026, 9, 30)


def _glossary_contracts() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id_contrato": ["CTR-T", "CTR-U"],
            "id_obra": ["OBR-T", "OBR-T"],
            "data_inicio": pd.to_datetime(["2026-03-16", "2026-01-05"]),
            "data_fim_atual": pd.to_datetime(["2026-06-16", "2026-12-05"]),
            "data_retirada": pd.to_datetime(["2026-06-10", "2026-06-20"]),
            "motivo_encerramento": ["concluido", "cancelado_cliente"],
            "valor_mensal": [10000.0, 5000.0],
        }
    )


def test_june_churn_and_zero_filled_months():
    kpis = monthly_kpis_from_pandas(monthly_from_pandas(_glossary_contracts(), REF), REF)

    assert list(kpis.index.strftime("%Y-%m")) == [
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
        "2026-06", "2026-07", "2026-08", "2026-09",
    ]
    assert kpis.loc[pd.Timestamp("2026-01-01"), "receita"] == pytest.approx(4354.84)

    june = kpis.loc[pd.Timestamp("2026-06-01")]
    assert (june["ativos_inicio"], june["retirados"], june["perdidos"]) == (2, 2, 1)
    assert june["churn_contratual_mes"] == pytest.approx(0.5)
    assert june["churn_financeiro_mes"] == pytest.approx(5000 / 15000, abs=1e-6)

    july = kpis.loc[pd.Timestamp("2026-07-01")]
    assert july["ativos_inicio"] == 0
    assert pd.isna(july["churn_contratual_mes"])
    assert kpis["churn_contratual_12m"].isna().all()  # só há 9 meses de histórico


def test_rolling_churn_is_a_ratio_of_sums_and_needs_twelve_months():
    months = pd.date_range("2025-01-01", periods=14, freq="MS")
    monthly = pd.DataFrame(
        {
            "mes": months,
            "receita_mes": 0.0,
            "ativo_no_inicio_mes": 10,
            "iniciou_no_mes": 0,
            "retirado_no_mes": 1,
            "perdido_no_mes": 1,
            "ativo_no_fim_mes": 9,
            "carteira_inicio_mes": 1000.0,
            "carteira_fim_mes": 900.0,
            "valor_perdido_mes": 100.0,
        }
    )
    # Em maio de 2025 a base é maior e as perdas também: 4 de 20 (20%).
    monthly.loc[4, ["ativo_no_inicio_mes", "perdido_no_mes", "carteira_inicio_mes", "valor_perdido_mes"]] = [
        20, 4, 2000.0, 400.0,
    ]
    kpis = monthly_kpis_from_pandas(monthly, date(2026, 2, 15))

    assert len(kpis) == 14
    assert kpis["churn_contratual_mes"].iloc[4] == pytest.approx(0.2)
    assert kpis["churn_contratual_12m"].iloc[:11].isna().all()
    # Razão das somas: (11 x 1 + 4) / (11 x 10 + 20) = 15 / 130. A média das taxas daria 0,1083.
    assert kpis["churn_contratual_12m"].iloc[11] == pytest.approx(15 / 130, abs=1e-6)
    assert kpis["churn_financeiro_12m"].iloc[11] == pytest.approx(1500 / 13000, abs=1e-6)


def test_compare_monthly_kpis_flags_differences_and_treats_both_nan_as_equal():
    expected = monthly_kpis_from_pandas(monthly_from_pandas(_glossary_contracts(), REF), REF)
    assert compare_monthly_kpis(expected, expected.copy()).empty

    actual = expected.copy()
    actual.loc[pd.Timestamp("2026-06-01"), "perdidos"] += 1
    actual.loc[pd.Timestamp("2026-05-01"), "receita"] += 0.01  # dentro da tolerância
    actual.loc[pd.Timestamp("2026-03-01"), "churn_contratual_mes"] += 0.01

    differences = compare_monthly_kpis(expected, actual)
    assert set(differences["coluna"]) == {"perdidos", "churn_contratual_mes"}
    assert (differences["id_contrato"] == "TOTAL").all()