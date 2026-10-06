from datetime import date

import pandas as pd

from src.etl.reconcile import compare_kpis, compare_monthly, kpis_from_pandas, monthly_from_pandas

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


def test_pandas_monthly_reproduces_the_glossary_example():
    monthly = monthly_from_pandas(_glossary_contracts(), REF)
    example = monthly[monthly["id_contrato"] == "CTR-T"].sort_values("mes")

    assert list(example["dias_ativos"]) == [16, 30, 31, 10]
    assert list(example["receita_mes"]) == [5161.29, 10000.0, 10000.0, 3333.33]
    assert round(example["receita_mes"].sum(), 2) == 28494.62

    first, last = example.iloc[0], example.iloc[-1]
    assert (first["ativo_no_inicio_mes"], first["iniciou_no_mes"], first["ativo_no_fim_mes"]) == (0, 1, 1)
    assert (last["ativo_no_inicio_mes"], last["retirado_no_mes"], last["ativo_no_fim_mes"]) == (1, 1, 0)

    june_loss = monthly[(monthly["id_contrato"] == "CTR-U") & (monthly["mes"] == "2026-06-01")].iloc[0]
    assert june_loss["perdido_no_mes"] == 1
    assert june_loss["valor_perdido_mes"] == 5000.0
    assert june_loss["ativo_no_inicio_mes"] == 1


def test_compare_monthly_reports_every_kind_of_difference():
    expected = monthly_from_pandas(_glossary_contracts(), REF)
    assert compare_monthly(expected, expected.copy()).empty

    actual = expected.copy()
    actual.loc[0, "dias_ativos"] += 1
    actual.loc[1, "receita_mes"] += 0.02
    actual.loc[2, "receita_mes"] += 0.004  # dentro da tolerância de arredondamento
    actual = actual.drop(index=3)

    differences = compare_monthly(expected, actual)
    assert set(differences["coluna"]) == {"dias_ativos", "receita_mes", "linha"}
    assert (differences["coluna"] == "receita_mes").sum() == 1


def test_kpis_from_pandas_on_a_small_example():
    obras = pd.DataFrame({"id_obra": ["OBR-T", "OBR-U", "OBR-V"], "qtd_portas": [40, 10, 20]})
    contratos = pd.DataFrame(
        {
            "id_contrato": ["CTR-T", "CTR-U", "CTR-V"],
            "id_obra": ["OBR-T", "OBR-T", "OBR-V"],
            "data_fim_atual": pd.to_datetime(["2026-06-16", "2026-12-05", "2026-08-01"]),
            "data_retirada": pd.to_datetime(["2026-06-10", "2026-06-20", None]),
            "valor_mensal": [10000.0, 5000.0, 3000.0],
        }
    )
    monthly = pd.DataFrame({"receita_mes": [100.0, 50.5]})

    assert kpis_from_pandas(obras, contratos, monthly, REF) == {
        "contratos_ativos": 1,
        "contratos_encerrados": 2,
        "carteira_ativa": 3000.0,
        "vencidos_em_aberto": 1,
        "obras_ativas": 1,
        "obras_encerradas": 1,
        "obras_sem_contrato": 1,
        "portas_em_operacao": 20,
        "receita_total": 150.5,
    }


def test_compare_kpis_flags_mismatches_and_respects_tolerance():
    expected = {"contratos_ativos": 90, "carteira_ativa": 1000.0, "receita_total": 500.0}
    actual = {"contratos_ativos": 89, "carteira_ativa": 1000.004, "receita_total": 500.04}
    result = compare_kpis(expected, actual).set_index("indicador")
    assert not result.loc["contratos_ativos", "ok"]
    assert result.loc["carteira_ativa", "ok"]
    assert result.loc["receita_total", "ok"]