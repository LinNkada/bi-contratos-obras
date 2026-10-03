"""Relatório de qualidade dos dados de origem.

Uso (a partir da raiz do projeto):
    python -m src.etl.quality
    python -m src.etl.quality --source data/raw --out-dir reports
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT, get_reference_date
from src.etl.extract import RAW_DIR, extract_all, read_cities
from src.etl.validate import CASCADE, RULE_DESCRIPTIONS, QualityResult, validate_all

logger = logging.getLogger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"


def format_report(result: QualityResult, reference_date: date, source: str) -> str:
    """Monta o relatório em Markdown."""
    summary = result.summary
    totals = summary[["recebidos", "validos", "rejeitados", "alertas"]].sum()
    rejection_rate = totals["rejeitados"] / totals["recebidos"] if totals["recebidos"] else 0.0

    lines = [
        "# Relatório de qualidade dos dados",
        "",
        f"- Origem: `{source}`",
        f"- Data de referência: {reference_date.isoformat()}",
        f"- Gerado em: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Resumo",
        "",
        "| Tabela | Recebidos | Válidos | Rejeitados | Alertas |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.tabela} | {row.recebidos} | {row.validos} | {row.rejeitados} | {row.alertas} |"
        )
    lines.append(
        f"| **Total** | {totals['recebidos']} | {totals['validos']} | "
        f"{totals['rejeitados']} | {totals['alertas']} |"
    )
    lines += ["", f"Taxa de rejeição: {rejection_rate:.1%}", "", "## Problemas por regra", ""]

    issues = result.issues
    if issues.empty:
        lines.append("Nenhum problema encontrado.")
    else:
        grouped = issues.groupby(["regra", "tabela", "severidade"]).size().reset_index(name="ocorrencias")
        grouped["ordem"] = grouped["regra"].eq(CASCADE)
        grouped = grouped.sort_values(["ordem", "regra", "tabela"])
        lines += [
            "| Regra | Tabela | Tratamento | Ocorrências | Descrição |",
            "|---|---|---|---:|---|",
        ]
        for row in grouped.itertuples(index=False):
            lines.append(
                f"| {row.regra} | {row.tabela} | {row.severidade} | {row.ocorrencias} | "
                f"{RULE_DESCRIPTIONS[row.regra]} |"
            )
        lines += [
            "",
            "Ocorrências contam problemas encontrados: um registro pode violar mais de uma regra.",
            "A lista completa, com a linha de cada problema, está em `problemas.csv`.",
        ]
        if (issues["regra"] == CASCADE).any():
            lines += [
                "",
                "Registros marcados como CASCATA foram rejeitados porque o cliente ou a obra "
                "de que dependem foi rejeitado.",
            ]
    return "\n".join(lines) + "\n"


def write_reports(result: QualityResult, out_dir: Path, reference_date: date, source: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "relatorio_qualidade.md"
    report_path.write_text(format_report(result, reference_date, source), encoding="utf-8")

    issues = result.issues.assign(descricao_regra=result.issues["regra"].map(RULE_DESCRIPTIONS))
    issues_path = out_dir / "problemas.csv"
    issues.to_csv(issues_path, index=False, encoding="utf-8", lineterminator="\n")
    logger.info("Wrote %s and %s", report_path, issues_path)


def log_summary(summary: pd.DataFrame) -> None:
    for row in summary.itertuples(index=False):
        logger.info(
            "%s | received: %d | valid: %d | rejected: %d | alerts: %d",
            row.tabela, row.recebidos, row.validos, row.rejeitados, row.alertas,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the source CSV files.")
    parser.add_argument("--source", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    reference_date = get_reference_date()
    sources = extract_all(args.source)
    result = validate_all(sources, read_cities(), reference_date)
    log_summary(result.summary)
    write_reports(result, args.out_dir, reference_date, str(args.source))


if __name__ == "__main__":
    main()