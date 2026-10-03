"""Synthetic data generator for the contracts and works scenario.

Usage (from the project root):
    python -m src.synthetic.generator
    python -m src.synthetic.generator --seed 7 --out-dir data/raw

Everything is fictitious. Business assumptions live in params.py.
"""
from __future__ import annotations

import argparse
import logging
import math
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT
from src.synthetic.params import SyntheticParams

logger = logging.getLogger(__name__)

CITIES_PATH = PROJECT_ROOT / "data" / "reference" / "ref_cidade.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"

KM_PER_DEGREE = 111.32
DAYS_PER_MONTH = 30

CLIENT_PREFIXES = ("Construtora", "Incorporadora", "Engenharia", "Empreendimentos", "Habitacional")
CLIENT_WORDS = (
    "Horizonte", "Aurora", "Vale Verde", "Monte Alto", "Cedro", "Atlântica",
    "Boreal", "Pioneira", "Jacarandá", "Solaris", "Itapuã", "Primavera",
    "Lumina", "Ouro Branco", "Serra Azul", "Delta", "Nobre", "Alvorada",
    "Bandeirante", "Cristal", "Imperial", "Orion", "Paraíso", "Sol Nascente",
)
WORK_PREFIXES = ("Edifício", "Residencial", "Condomínio", "Torre")
WORK_WORDS = (
    "Mirante do Sol", "Bosque Alto", "Jardins", "Colina Verde", "Porto Seguro",
    "Quinta das Flores", "Praça Nova", "Lago Azul", "Vista Linda", "Recanto",
    "Belvedere", "Alameda Real", "Parque das Águas", "Morada do Vale", "Terraço",
    "Montanhês", "Chácara Nova", "Villa Rica", "Bela Aliança", "Mar e Serra",
    "Esmeralda", "Safira", "Topázio", "Rubi", "Diamante", "Opala",
    "Ametista", "Coral", "Pérola", "Granada",
)

OBRA_COLUMNS = [
    "id_obra", "id_cliente", "nome_obra", "cidade", "estado",
    "latitude", "longitude", "qtd_portas",
]
CONTRATO_COLUMNS = [
    "id_contrato", "id_obra", "data_inicio", "data_fim_prevista_inicial",
    "data_fim_atual", "data_retirada", "motivo_encerramento", "valor_mensal",
]
CSV_DECIMALS = {"latitude": 6, "longitude": 6, "valor_mensal": 2}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def load_cities(path: Path = CITIES_PATH) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def unique_names(
    rng: np.random.Generator, prefixes: Sequence[str], words: Sequence[str], n: int
) -> list[str]:
    combos = [f"{prefix} {word}" for prefix in prefixes for word in words]
    if n > len(combos):
        raise ValueError(f"Cannot create {n} unique names: only {len(combos)} combinations")
    chosen = rng.choice(len(combos), size=n, replace=False)
    return [combos[int(i)] for i in chosen]


def jitter_coordinates(
    rng: np.random.Generator, lat: float, lon: float, max_km: float
) -> tuple[float, float]:
    """Move a point up to max_km away from the city center."""
    radius = max_km * math.sqrt(rng.random())
    angle = rng.random() * 2 * math.pi
    d_lat = radius * math.cos(angle) / KM_PER_DEGREE
    d_lon = radius * math.sin(angle) / (KM_PER_DEGREE * math.cos(math.radians(lat)))
    return round(lat + d_lat, 6), round(lon + d_lon, 6)


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def month_starts(start: date, end: date) -> list[date]:
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = _next_month(current)
    return months


def start_month_weights(p: SyntheticParams, months: list[date]) -> np.ndarray:
    raw = np.array(
        [
            (1 + p.annual_growth) ** (i / 12) * p.monthly_seasonality[month.month - 1]
            for i, month in enumerate(months)
        ]
    )
    return raw / raw.sum()


def draw_start_date(
    rng: np.random.Generator, p: SyntheticParams, months: list[date], weights: np.ndarray
) -> date:
    month = months[int(rng.choice(len(months), p=weights))]
    first_day = max(month, p.history_start)
    last_day = min(_next_month(month) - timedelta(days=1), p.reference_date)
    offset = int(rng.integers(0, (last_day - first_day).days + 1))
    return first_day + timedelta(days=offset)


def draw_additional_start(
    rng: np.random.Generator, p: SyntheticParams, first_start: date
) -> date:
    if rng.random() < p.simultaneous_contract_prob:
        offset = int(rng.integers(0, 31))
    else:
        offset = int(rng.integers(31, p.max_extra_contract_offset_days + 1))
    return min(first_start + timedelta(days=offset), p.reference_date)


# --------------------------------------------------------------------------
# Contract timeline
# --------------------------------------------------------------------------
def _signing_offset_days(rng: np.random.Generator, p: SyntheticParams) -> int:
    """Days between the current term end and the signing of its extension."""
    if rng.random() < p.late_extension_prob:
        return int(rng.integers(1, p.extension_delay_max_days + 1))
    return -int(rng.integers(0, p.extension_lead_max_days + 1))


def build_term_chain(
    rng: np.random.Generator,
    p: SyntheticParams,
    start: date,
    initial_end: date,
    actual_end: date,
) -> list[tuple[date, date]]:
    """Original term and each extension, as (term_end, signed_on)."""
    chain = [(initial_end, start)]
    current_end = initial_end
    while current_end < actual_end:
        gap_days = (actual_end - current_end).days
        step_days = min(
            int(rng.choice(p.extension_months, p=p.extension_weights)) * DAYS_PER_MONTH,
            math.ceil(gap_days / DAYS_PER_MONTH) * DAYS_PER_MONTH,
        )
        signed_on = current_end + timedelta(days=_signing_offset_days(rng, p))
        current_end = current_end + timedelta(days=step_days)
        chain.append((current_end, signed_on))
    return chain


def simulate_timeline(
    rng: np.random.Generator, p: SyntheticParams, start: date
) -> dict[str, date | str | None]:
    """Simulate the real life of a contract and what is visible on the reference date."""
    term_days = int(rng.choice(p.term_months, p=p.term_weights)) * DAYS_PER_MONTH
    initial_end = start + timedelta(days=term_days)

    outcome = str(rng.choice(p.outcomes, p=p.outcome_weights))
    if outcome != "concluido":
        duration = term_days * rng.uniform(*p.cancellation_fraction)
    elif rng.random() < p.extended_prob:
        duration = term_days * (1 + rng.uniform(*p.overrun_range))
    else:
        duration = term_days * rng.uniform(*p.early_finish_range)
    actual_end = start + timedelta(days=max(1, int(round(float(duration)))))

    chain = build_term_chain(rng, p, start, initial_end, actual_end)

    if actual_end <= p.reference_date:
        return {
            "data_fim_prevista_inicial": initial_end,
            "data_fim_atual": chain[-1][0],
            "data_retirada": actual_end,
            "motivo_encerramento": outcome,
        }
    known_ends = [end for end, signed_on in chain if signed_on <= p.reference_date]
    return {
        "data_fim_prevista_inicial": initial_end,
        "data_fim_atual": max(known_ends),
        "data_retirada": None,
        "motivo_encerramento": None,
    }


def monthly_value(
    rng: np.random.Generator, p: SyntheticParams, start: date, doors: int
) -> float:
    years = (start - p.history_start).days / 365.25
    price = (
        p.base_price_per_door
        * (1 + p.annual_price_adjustment) ** years
        * rng.lognormal(0.0, p.price_sigma)
    )
    return round(doors * float(price), 2)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
def build_obras(rng: np.random.Generator, p: SyntheticParams, cities: pd.DataFrame) -> pd.DataFrame:
    weights = cities["peso"].to_numpy(dtype=float)
    weights = weights / weights.sum()
    city_positions = rng.choice(len(cities), size=p.n_works, p=weights)
    names = unique_names(rng, WORK_PREFIXES, WORK_WORDS, p.n_works)

    rows = []
    for i in range(p.n_works):
        city = cities.iloc[int(city_positions[i])]
        lat, lon = jitter_coordinates(
            rng, float(city["latitude"]), float(city["longitude"]), p.max_jitter_km
        )
        doors = int(round(float(rng.lognormal(math.log(p.doors_median), p.doors_sigma))))
        rows.append(
            {
                "id_obra": f"OBR-{i + 1:04d}",
                "nome_obra": names[i],
                "cidade": city["cidade"],
                "estado": city["estado"],
                "latitude": lat,
                "longitude": lon,
                "qtd_portas": min(max(doors, p.doors_min), p.doors_max),
            }
        )
    return pd.DataFrame(rows)


def assign_clients(rng: np.random.Generator, p: SyntheticParams) -> np.ndarray:
    """Client index for each work: everyone owns at least one, a few own many."""
    weights = rng.lognormal(0.0, p.client_concentration_sigma, size=p.n_clients)
    weights = weights / weights.sum()
    extra = rng.multinomial(p.n_works - p.n_clients, weights)
    assignment = np.repeat(np.arange(p.n_clients), 1 + extra)
    return rng.permutation(assignment)


def build_contratos(
    rng: np.random.Generator, p: SyntheticParams, obras: pd.DataFrame
) -> pd.DataFrame:
    months = month_starts(p.history_start, p.reference_date)
    weights = start_month_weights(p, months)

    rows = []
    for obra in obras.itertuples(index=False):
        n_contracts = int(rng.choice(p.contracts_per_work, p=p.contracts_per_work_weights))
        # A small work cannot be split into contracts with almost no doors.
        n_contracts = max(1, min(n_contracts, obra.qtd_portas // p.min_doors_per_contract))
        shares = np.ones(1) if n_contracts == 1 else rng.dirichlet(np.full(n_contracts, 4.0))
        first_start = draw_start_date(rng, p, months, weights)
        for j in range(n_contracts):
            start = first_start if j == 0 else draw_additional_start(rng, p, first_start)
            timeline = simulate_timeline(rng, p, start)
            covered_doors = max(
                p.min_doors_per_contract, int(round(float(shares[j]) * obra.qtd_portas))
            )
            rows.append(
                {
                    "id_obra": obra.id_obra,
                    "data_inicio": start,
                    **timeline,
                    "valor_mensal": monthly_value(rng, p, start, covered_doors),
                }
            )

    contratos = pd.DataFrame(rows)
    contratos = contratos.sort_values(["data_inicio", "id_obra"], kind="stable").reset_index(drop=True)
    contratos.insert(0, "id_contrato", [f"CTR-{i:04d}" for i in range(1, len(contratos) + 1)])
    return contratos[CONTRATO_COLUMNS]


def build_clientes(
    rng: np.random.Generator, p: SyntheticParams, obras: pd.DataFrame, contratos: pd.DataFrame
) -> pd.DataFrame:
    names = unique_names(rng, CLIENT_PREFIXES, CLIENT_WORDS, p.n_clients)

    first_start: dict[str, date] = {}
    merged = contratos.merge(obras[["id_obra", "id_cliente"]], on="id_obra")
    for row in merged.itertuples(index=False):
        current = first_start.get(row.id_cliente)
        if current is None or row.data_inicio < current:
            first_start[row.id_cliente] = row.data_inicio

    rows = []
    for i, name in enumerate(names, start=1):
        client_id = f"CLI-{i:04d}"
        low, high = p.registration_lead_days
        lead = int(rng.integers(low, high + 1))
        rows.append(
            {
                "id_cliente": client_id,
                "nome_cliente": name,
                "data_cadastro": first_start[client_id] - timedelta(days=lead),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def generate_dataset(
    p: SyntheticParams | None = None, cities_path: Path = CITIES_PATH
) -> dict[str, pd.DataFrame]:
    p = p or SyntheticParams()
    if p.n_works < p.n_clients:
        raise ValueError("n_works must be at least n_clients")

    rng = np.random.default_rng(p.seed)
    cities = load_cities(cities_path)

    obras = build_obras(rng, p, cities)
    client_positions = assign_clients(rng, p)
    obras.insert(1, "id_cliente", [f"CLI-{int(i) + 1:04d}" for i in client_positions])
    contratos = build_contratos(rng, p, obras)
    clientes = build_clientes(rng, p, obras, contratos)

    return {"cliente": clientes, "obra": obras[OBRA_COLUMNS], "contrato": contratos}


def write_csvs(datasets: dict[str, pd.DataFrame], out_dir: Path = OUTPUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in datasets.items():
        out = df.copy()
        for column, decimals in CSV_DECIMALS.items():
            if column in out.columns:
                out[column] = out[column].map(lambda x, d=decimals: f"{x:.{d}f}")
        path = out_dir / f"{name}.csv"
        out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        logger.info("Wrote %s (%d rows)", path, len(out))


def summarize(datasets: dict[str, pd.DataFrame], reference_date: date) -> None:
    contratos = datasets["contrato"]
    active = contratos["data_retirada"].isna()
    ended = ~active
    extended = contratos["data_fim_atual"] > contratos["data_fim_prevista_inicial"]
    overdue = active & (contratos["data_fim_atual"] < reference_date)

    logger.info(
        "Clients: %d | Works: %d | Contracts: %d",
        len(datasets["cliente"]), len(datasets["obra"]), len(contratos),
    )
    logger.info(
        "Active: %d | Ended: %d | Overdue and still installed: %d",
        active.sum(), ended.sum(), overdue.sum(),
    )
    if ended.any():
        logger.info("Extended among ended contracts: %.0f%%", 100 * extended[ended].mean())
        logger.info("Ended by reason: %s", contratos.loc[ended, "motivo_encerramento"].value_counts().to_dict())
    values = contratos["valor_mensal"]
    logger.info(
        "Monthly value: min %.2f | median %.2f | max %.2f",
        values.min(), values.median(), values.max(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic CSV files.")
    parser.add_argument("--seed", type=int, default=SyntheticParams().seed)
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    params = SyntheticParams(seed=args.seed)
    datasets = generate_dataset(params)
    write_csvs(datasets, args.out_dir)
    summarize(datasets, params.reference_date)


if __name__ == "__main__":
    main()