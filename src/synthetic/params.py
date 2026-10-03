"""Parameters of the synthetic data generator.

Glossary (code in English, data in Portuguese):
    client = cliente, work = obra, doors = portas, term = prazo,
    extension = prorrogação, outcome = desfecho (motivo de encerramento).

Every number here is fictitious: do not use real prices or real volumes.
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
    client_concentration_sigma: float = 0.9  # higher = a few clients own most works

    # Works
    doors_median: int = 40
    doors_sigma: float = 0.55
    doors_min: int = 8
    doors_max: int = 200
    max_jitter_km: float = 8.0  # maximum distance from the city center

    # Contracts per work
    contracts_per_work: tuple[int, ...] = (1, 2, 3)
    contracts_per_work_weights: tuple[float, ...] = (0.62, 0.28, 0.10)
    simultaneous_contract_prob: float = 0.40
    max_extra_contract_offset_days: int = 240
    min_doors_per_contract: int = 4

    # Start dates: growth over the years and seasonality (January..December)
    annual_growth: float = 0.20
    monthly_seasonality: tuple[float, ...] = (
        0.7, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.6,
    )

    # Initial term
    term_months: tuple[int, ...] = (6, 9, 12, 15, 18, 24)
    term_weights: tuple[float, ...] = (0.15, 0.20, 0.30, 0.15, 0.12, 0.08)

    # How the contract really ends
    outcomes: tuple[str, ...] = ("concluido", "cancelado_cliente", "rescindido")
    outcome_weights: tuple[float, ...] = (0.90, 0.06, 0.04)
    cancellation_fraction: tuple[float, float] = (0.2, 0.8)  # share of the term served

    # Extensions (prorrogações)
    extended_prob: float = 0.70
    overrun_range: tuple[float, float] = (0.10, 0.80)  # extra time over the term
    early_finish_range: tuple[float, float] = (0.85, 1.0)
    extension_months: tuple[int, ...] = (1, 2, 3, 4, 6)
    extension_weights: tuple[float, ...] = (0.30, 0.25, 0.20, 0.15, 0.10)
    late_extension_prob: float = 0.08  # extension signed after the term ended
    extension_lead_max_days: int = 15
    extension_delay_max_days: int = 30

    # Price per door per month (fictitious)
    base_price_per_door: float = 85.0
    price_sigma: float = 0.15
    annual_price_adjustment: float = 0.05

    # A client registers shortly before the first contract
    registration_lead_days: tuple[int, int] = (7, 90)