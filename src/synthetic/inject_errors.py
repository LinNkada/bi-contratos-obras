"""Injeta erros controlados na base limpa, para demonstrar a validação.

Uso (a partir da raiz do projeto):
    python -m src.synthetic.inject_errors
    python -m src.synthetic.inject_errors --source data/raw --out-dir data/raw_sujo --seed 7

Cada tipo de erro é injetado uma vez, de modo que todas as regras de validação
(R01 a R23) e a rejeição em cascata tenham ao menos um caso. O manifesto
(_erros_injetados.csv) lista o que foi injetado e quais regras devem disparar.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import PROJECT_ROOT, get_reference_date
from src.etl.extract import RAW_DIR, extract_all

logger = logging.getLogger(__name__)

DIRTY_DIR = PROJECT_ROOT / "data" / "raw_sujo"
DEFAULT_SEED = 7
MANIFEST_NAME = "_erros_injetados.csv"
MANIFEST_COLUMNS = ["tabela", "linha", "id_registro", "regras_esperadas", "descricao"]
ID_COLUMNS = {"cliente": "id_cliente", "obra": "id_obra", "contrato": "id_contrato"}


@dataclass(frozen=True)
class Injection:
    table: str
    index: int  # posição na tabela (a linha no CSV é index + 2)
    rules: tuple[str, ...]
    description: str


def _iso(d: date) -> str:
    return d.isoformat()


class ErrorInjector:
    """Aplica os erros sobre uma cópia dos dados e guarda o que foi feito."""

    def __init__(
        self, clean: dict[str, pd.DataFrame], reference_date: date, seed: int = DEFAULT_SEED
    ) -> None:
        self.clean = clean
        self.ref = reference_date
        self.rng = np.random.default_rng(seed)
        self.tables = {name: df.copy() for name, df in clean.items()}
        self.used: dict[str, set[int]] = {name: set() for name in clean}
        self.injections: list[Injection] = []
        self.cascade_client = ""
        self.cascade_works: set[str] = set()

    # ----------------------------------------------------------------------
    # Ferramentas
    # ----------------------------------------------------------------------
    def _pick(self, table: str, candidates: list[int]) -> int:
        """Sorteia um registro ainda não usado entre os candidatos."""
        pool = [i for i in candidates if i not in self.used[table]]
        if not pool:
            raise ValueError(f"No eligible record left in {table} to inject an error")
        chosen = int(self.rng.choice(pool))
        self.used[table].add(chosen)
        return chosen

    def _copy_with(self, table: str, source: int, **changes: str) -> dict[str, str]:
        values = self.tables[table].loc[source].to_dict()
        values.update(changes)
        return values

    def _append(self, table: str, values: dict[str, str]) -> int:
        df = self.tables[table]
        df.loc[len(df)] = [values[column] for column in df.columns]
        index = len(df) - 1
        self.used[table].add(index)
        return index

    def _record(self, table: str, index: int, rules: list[str], description: str) -> None:
        self.injections.append(Injection(table, index, tuple(rules), description))

    def _choose_cascade_client(self) -> str:
        """Cliente com menos contratos: assim a cascata fica pequena."""
        obras = self.tables["obra"]
        owner = dict(zip(obras["id_obra"], obras["id_cliente"]))
        counts = {client: 0 for client in self.tables["cliente"]["id_cliente"]}
        for work_id in self.tables["contrato"]["id_obra"]:
            counts[owner[work_id]] += 1
        return min(counts, key=lambda client: (counts[client], client))

    # ----------------------------------------------------------------------
    # Execução
    # ----------------------------------------------------------------------
    def run(self) -> None:
        obras = self.tables["obra"]
        self.cascade_client = self._choose_cascade_client()
        self.cascade_works = set(obras.loc[obras["id_cliente"] == self.cascade_client, "id_obra"])
        self._inject_clientes()
        self._inject_obras()
        self._inject_contratos()

    def _inject_clientes(self) -> None:
        clientes = self.tables["cliente"]
        candidates = [i for i in clientes.index if clientes.at[i, "id_cliente"] != self.cascade_client]

        source = self._pick("cliente", candidates)
        index = self._append("cliente", self._copy_with("cliente", source))
        self._record("cliente", index, ["R01"], "id_cliente duplicado de um cliente existente")

        index = self._append(
            "cliente",
            {"id_cliente": "", "nome_cliente": "", "data_cadastro": "2024-05-10"},
        )
        self._record("cliente", index, ["R01", "R02"], "id_cliente e nome_cliente vazios")

        index = self._append(
            "cliente",
            {"id_cliente": "CLI-9001", "nome_cliente": "Incorporadora Teste", "data_cadastro": "2024-02-30"},
        )
        self._record("cliente", index, ["R03"], "data_cadastro com data inexistente")

        # Cascata: o cliente com menos contratos passa a ter cadastro no futuro.
        cascade_index = int(clientes.index[clientes["id_cliente"] == self.cascade_client][0])
        clientes.at[cascade_index, "data_cadastro"] = _iso(self.ref + timedelta(days=120))
        self.used["cliente"].add(cascade_index)
        self._record("cliente", cascade_index, ["R03"], "data_cadastro posterior à data de referência")

        obras = self.tables["obra"]
        contratos = self.tables["contrato"]
        for i in obras.index[obras["id_cliente"] == self.cascade_client]:
            self._record("obra", int(i), ["CASCATA"], "obra do cliente rejeitado")
        for i in contratos.index[contratos["id_obra"].isin(self.cascade_works)]:
            self._record("contrato", int(i), ["CASCATA"], "contrato de obra rejeitada")

    def _inject_obras(self) -> None:
        obras = self.tables["obra"]
        candidates = [i for i in obras.index if obras.at[i, "id_cliente"] != self.cascade_client]

        source = self._pick("obra", candidates)
        index = self._append("obra", self._copy_with("obra", source))
        self._record("obra", index, ["R04"], "id_obra duplicado de uma obra existente")

        source = self._pick("obra", candidates)
        values = self._copy_with(
            "obra", source, id_obra="OBR-9001", id_cliente="CLI-9999", nome_obra=""
        )
        index = self._append("obra", values)
        self._record("obra", index, ["R05", "R06"], "cliente inexistente e nome_obra vazio")

        source = self._pick("obra", candidates)
        values = self._copy_with("obra", source, id_obra="OBR-9002", estado="XX", qtd_portas="0")
        index = self._append("obra", values)
        self._record("obra", index, ["R07", "R10"], "UF inválida e qtd_portas zero")

        source = self._pick("obra", candidates)
        values = self._copy_with("obra", source, id_obra="OBR-9003", longitude="10.0", qtd_portas="abc")
        index = self._append("obra", values)
        self._record("obra", index, ["R08", "R10"], "longitude fora do Brasil e qtd_portas não numérica")

        source = self._pick("obra", candidates)
        shifted_lat = float(obras.at[source, "latitude"]) + 0.5
        values = self._copy_with("obra", source, id_obra="OBR-9004", latitude=f"{shifted_lat:.6f}")
        index = self._append("obra", values)
        self._record("obra", index, ["R09", "R11"], "coordenadas a cerca de 55 km da cidade e obra sem contrato")

    def _inject_contratos(self) -> None:
        contratos = self.tables["contrato"]
        candidates = [i for i in contratos.index if contratos.at[i, "id_obra"] not in self.cascade_works]
        ended = [i for i in candidates if contratos.at[i, "data_retirada"] != ""]
        active = [i for i in candidates if contratos.at[i, "data_retirada"] == ""]

        def start_of(i: int) -> date:
            return date.fromisoformat(contratos.at[i, "data_inicio"])

        source = self._pick("contrato", candidates)
        index = self._append("contrato", self._copy_with("contrato", source))
        self._record("contrato", index, ["R12"], "id_contrato duplicado de um contrato existente")

        i = self._pick("contrato", candidates)
        contratos.at[i, "id_contrato"] = ""
        contratos.at[i, "id_obra"] = "OBR-9999"
        self._record("contrato", i, ["R12", "R13"], "id_contrato vazio e obra inexistente")

        i = self._pick("contrato", candidates)
        contratos.at[i, "data_inicio"] = "31/03/2024"
        self._record("contrato", i, ["R14"], "data_inicio em formato inválido")

        i = self._pick("contrato", candidates)
        start = start_of(i)
        contratos.at[i, "data_fim_prevista_inicial"] = _iso(start - timedelta(days=30))
        contratos.at[i, "data_fim_atual"] = _iso(start - timedelta(days=60))
        self._record("contrato", i, ["R15", "R16"], "prazos anteriores ao início do contrato")

        i = self._pick("contrato", ended)
        contratos.at[i, "data_retirada"] = _iso(start_of(i) - timedelta(days=10))
        self._record("contrato", i, ["R17"], "data_retirada anterior ao início")

        i = self._pick("contrato", ended)
        contratos.at[i, "data_retirada"] = _iso(self.ref + timedelta(days=45))
        contratos.at[i, "valor_mensal"] = "-100.00"
        self._record("contrato", i, ["R17", "R20"], "data_retirada no futuro e valor negativo")

        i = self._pick("contrato", ended)
        contratos.at[i, "motivo_encerramento"] = ""
        self._record("contrato", i, ["R18"], "data_retirada sem motivo_encerramento")

        i = self._pick("contrato", active)
        contratos.at[i, "motivo_encerramento"] = "cancelado"
        self._record("contrato", i, ["R18", "R19"], "motivo fora do domínio e sem data_retirada")

        i = self._pick("contrato", active)
        future_start = self.ref + timedelta(days=10)
        contratos.at[i, "data_inicio"] = _iso(future_start)
        contratos.at[i, "data_fim_prevista_inicial"] = _iso(future_start + timedelta(days=365))
        contratos.at[i, "data_fim_atual"] = _iso(future_start + timedelta(days=365))
        self._record("contrato", i, ["R21"], "data_inicio posterior à data de referência")

        i = self._pick("contrato", candidates)
        owner = dict(zip(self.clean["obra"]["id_obra"], self.clean["obra"]["id_cliente"]))
        registration = dict(zip(self.clean["cliente"]["id_cliente"], self.clean["cliente"]["data_cadastro"]))
        registered_on = date.fromisoformat(registration[owner[contratos.at[i, "id_obra"]]])
        contratos.at[i, "data_inicio"] = _iso(registered_on - timedelta(days=20))
        self._record("contrato", i, ["R22"], "data_inicio anterior ao cadastro do cliente")

        source = self._pick("contrato", candidates)
        values = self._copy_with("contrato", source, id_contrato="CTR-9001")
        index = self._append("contrato", values)
        self._record("contrato", index, ["R23"], "contrato igual a outro (mesma obra, início e valor)")

    # ----------------------------------------------------------------------
    # Resultado
    # ----------------------------------------------------------------------
    def build_manifest(self) -> pd.DataFrame:
        rows = []
        for injection in self.injections:
            df = self.tables[injection.table]
            rows.append(
                {
                    "tabela": injection.table,
                    "linha": injection.index + 2,  # a linha 1 do CSV é o cabeçalho
                    "id_registro": df.at[injection.index, ID_COLUMNS[injection.table]],
                    "regras_esperadas": ",".join(injection.rules),
                    "descricao": injection.description,
                }
            )
        return pd.DataFrame(rows, columns=MANIFEST_COLUMNS)


def inject_errors(
    clean: dict[str, pd.DataFrame], reference_date: date, seed: int = DEFAULT_SEED
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Devolve as tabelas com erros e o manifesto. Os dados de entrada não são alterados."""
    injector = ErrorInjector(clean, reference_date, seed)
    injector.run()
    return injector.tables, injector.build_manifest()


def write_dirty(tables: dict[str, pd.DataFrame], manifest: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8", lineterminator="\n")
    manifest.to_csv(out_dir / MANIFEST_NAME, index=False, encoding="utf-8", lineterminator="\n")
    logger.info("Wrote dirty files and %d manifest entries to %s", len(manifest), out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject controlled errors into the clean CSV files.")
    parser.add_argument("--source", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=DIRTY_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    tables, manifest = inject_errors(extract_all(args.source), get_reference_date(), args.seed)
    write_dirty(tables, manifest, args.out_dir)


if __name__ == "__main__":
    main()