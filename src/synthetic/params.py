"""Parâmetros do gerador de dados sintéticos.

Glossário (código em inglês, dados em português):
    client = cliente, work = obra, doors = portas, term = prazo,
    extension = prorrogação, outcome = desfecho (motivo de encerramento).

Todos os números daqui são fictícios: não use preços nem volumes reais.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SyntheticParams:
    seed: int = 42
    reference_date: date = date(2026, 9, 30)
    history_start: date = date(2023, 10, 1)

    # Volume
    n_clients: int = 40
    n_works: int = 100
    client_concentration_sigma: float = 0.9  # maior = poucos clientes concentram as obras

    # Obras
    doors_median: int = 40
    doors_sigma: float = 0.55
    doors_min: int = 8
    doors_max: int = 200
    max_jitter_km: float = 8.0  # distância máxima até o centro da cidade

    # Contratos por obra
    contracts_per_work: tuple[int, ...] = (1, 2, 3)
    contracts_per_work_weights: tuple[float, ...] = (0.62, 0.28, 0.10)
    simultaneous_contract_prob: float = 0.40
    max_extra_contract_offset_days: int = 240
    min_doors_per_contract: int = 4  # evita contratos com uma ou duas portas

    # Datas de início: crescimento ao longo dos anos e sazonalidade (janeiro a dezembro)
    annual_growth: float = 0.20
    monthly_seasonality: tuple[float, ...] = (
        0.7, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.6,
    )

    # Prazo inicial do contrato
    term_months: tuple[int, ...] = (6, 9, 12, 15, 18, 24)
    term_weights: tuple[float, ...] = (0.15, 0.20, 0.30, 0.15, 0.12, 0.08)

    # Como o contrato termina de verdade
    outcomes: tuple[str, ...] = ("concluido", "cancelado_cliente", "rescindido")
    outcome_weights: tuple[float, ...] = (0.90, 0.06, 0.04)
    cancellation_fraction: tuple[float, float] = (0.2, 0.8)  # parte do prazo cumprida

    # Prorrogações
    extended_prob: float = 0.70
    overrun_range: tuple[float, float] = (0.10, 0.80)  # tempo extra além do prazo
    early_finish_range: tuple[float, float] = (0.85, 1.0)  # término antes do prazo
    extension_months: tuple[int, ...] = (1, 2, 3, 4, 6)
    extension_weights: tuple[float, ...] = (0.30, 0.25, 0.20, 0.15, 0.10)
    late_extension_prob: float = 0.20  # prorrogação assinada depois do fim do prazo
    extension_lead_max_days: int = 15  # antecedência máxima da assinatura
    extension_delay_max_days: int = 90  # atraso máximo da assinatura

    # Preço por porta ao mês (fictício)
    base_price_per_door: float = 85.0
    price_sigma: float = 0.15
    annual_price_adjustment: float = 0.05

    # O cliente se cadastra pouco antes do primeiro contrato
    registration_lead_days: tuple[int, int] = (7, 90)