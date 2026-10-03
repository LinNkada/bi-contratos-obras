"""Extração: leitura dos CSVs de origem como texto, sem nenhuma conversão."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CITIES_PATH = PROJECT_ROOT / "data" / "reference" / "ref_cidade.csv"

SOURCE_COLUMNS = {
    "cliente": ["id_cliente", "nome_cliente", "data_cadastro"],
    "obra": [
        "id_obra", "id_cliente", "nome_obra", "cidade", "estado",
        "latitude", "longitude", "qtd_portas",
    ],
    "contrato": [
        "id_contrato", "id_obra", "data_inicio", "data_fim_prevista_inicial",
        "data_fim_atual", "data_retirada", "motivo_encerramento", "valor_mensal",
    ],
}


def read_source(name: str, directory: Path = RAW_DIR) -> pd.DataFrame:
    """Lê um CSV de origem. Tudo entra como texto: quem valida é a etapa seguinte."""
    path = directory / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    missing = [column for column in SOURCE_COLUMNS[name] if column not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    return df[SOURCE_COLUMNS[name]]


def extract_all(directory: Path = RAW_DIR) -> dict[str, pd.DataFrame]:
    sources = {name: read_source(name, directory) for name in SOURCE_COLUMNS}
    for name, df in sources.items():
        logger.info("Read %s: %d records", name, len(df))
    return sources


def read_cities(path: Path = CITIES_PATH) -> pd.DataFrame:
    """Tabela de referência de cidades, usada para conferir as coordenadas."""
    return pd.read_csv(path, encoding="utf-8")