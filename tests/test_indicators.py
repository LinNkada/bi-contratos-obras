from datetime import date

import pandas as pd
import pytest

from src.etl.indicators import expiry_indicators_from_pandas, rehire_indicators_from_pandas
REF = date(2026, 9, 30)


def _portfolio() -> tuple[pd.DataFrame, pd.DataFrame]:
    obras = pd.DataFrame(
        {
            "id_obra": ["OBR-1", "OBR-2", "OBR-3", "OBR-4", "OBR-5"],
            "id_cliente": ["CLI-1", "CLI-1", "CLI-2", "CLI-3", "CLI-4"],
        }
    )
    contratos = pd.DataFrame(
        {
            "id_contrato": ["K1", "K2", "K3", "K4", "K5", "K6"],
            "id_obra": ["OBR-1", "OBR-2", "OBR-3", "OBR-4", "OBR-5", "OBR-5"],
            "data_inicio": pd.to_datetime(
                ["2026-01-10", "2026-01-10", "2026-02-01", "2026-03-01", "2025-01-01", "2025-03-01"]
            ),
            "data_fim_prevista_inicial": pd.to_datetime(
                ["2026-04-10", "2027-04-18", "2026-11-14", "2026-09-10", "2025-07-01", "2025-09-01"]
            ),
            "data_fim_atual": pd.to_datetime(
                ["2026-10-20", "2027-04-18", "2026-11-14", "2026-09-20", "2025-09-01", "2025-09-01"]
            ),
            "data_retirada": pd.to_datetime([None, None, None, None, "2025-09-15", "2025-08-20"]),
            "valor_mensal": [1000.0, 2000.0, 3000.0, 500.0, 700.0, 400.0],
        }
    )
    return obras, contratos


def test_bands_and_risk_on_a_small_portfolio():
    obras, contratos = _portfolio()
    kpis = expiry_indicators_from_pandas(obras, contratos, REF)

    # K1 vence em 20 dias, mas o cliente tem o K2 até 2027: não é risco.
    assert kpis["receita_a_vencer_0_30"] == 1000.0
    assert kpis["receita_em_risco_0_30"] == 0.0
    # K3 vence em 45 dias e o cliente não tem mais nada: é risco.
    assert kpis["receita_a_vencer_31_60"] == 3000.0
    assert kpis["receita_em_risco_31_60"] == 3000.0
    assert kpis["receita_a_vencer_61_90"] == 0.0
    # K4 já passou do prazo e segue instalado.
    assert kpis["vencidos_em_aberto_valor"] == 500.0


def test_rates_durations_and_expected_revenue():
    obras, contratos = _portfolio()
    kpis = expiry_indicators_from_pandas(obras, contratos, REF)

    # Prazo inicial resolvido: K1, K4, K5 e K6. Prorrogados entre eles: K1, K4 e K5.
    assert kpis["taxa_prorrogacao"] == pytest.approx(0.75)
    # Entre os encerrados (K5 e K6), só o K5 foi prorrogado.
    assert kpis["taxa_prorrogacao_encerrados"] == pytest.approx(0.5)
    assert kpis["desvio_prazo_medio_dias"] == pytest.approx(32.0)  # (76 + -12) / 2
    assert kpis["duracao_real_media_dias"] == pytest.approx(214.5)  # (257 + 172) / 2
    assert kpis["duracao_prevista_media_dias"] == pytest.approx(232.83)
    # (1000 + 3000) x (1 - 0,75)
    assert kpis["receita_a_vencer_esperada_90"] == pytest.approx(1000.0)

def test_rehire_rate_uses_only_complete_windows():
    obras = pd.DataFrame(
        {
            "id_obra": ["OBR-A", "OBR-B", "OBR-C", "OBR-D", "OBR-E"],
            "id_cliente": ["CLI-1", "CLI-1", "CLI-2", "CLI-3", "CLI-4"],
        }
    )
    contratos = pd.DataFrame(
        {
            "id_contrato": ["A", "B", "C", "D", "E"],
            "id_obra": ["OBR-A", "OBR-B", "OBR-C", "OBR-D", "OBR-E"],
            "data_inicio": pd.to_datetime(
                ["2023-10-01", "2024-06-01", "2024-01-01", "2025-12-01", "2026-05-01"]
            ),
            "data_retirada": pd.to_datetime(
                ["2024-01-10", "2025-02-01", "2024-03-01", "2026-06-01", None]
            ),
        }
    )
    kpis = rehire_indicators_from_pandas(obras, contratos, REF)

    # Janela completa: A, B e C. D encerrou há menos de 12 meses e E está ativo.
    # Só o A foi recontratado (o cliente CLI-1 iniciou o B em 2024-06-01).
    assert kpis["recontratacao_base"] == 3
    assert kpis["taxa_recontratacao_12m"] == pytest.approx(0.3333, abs=1e-4)