"""Pipeline completo: extração, validação, transformação e carga no MySQL.

Uso (a partir da raiz do projeto):
    python -m src.pipeline
    python -m src.pipeline --source data/raw_sujo
    python -m src.pipeline --reset-schema     # apaga e recria as tabelas antes
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from src.config import PROJECT_ROOT, load_settings
from src.db import get_engine
from src.etl.extract import RAW_DIR, extract_all, read_cities
from src.etl.load import fail_execution, load_all, start_execution
from src.etl.quality import REPORTS_DIR, log_summary, write_reports
from src.etl.schema import apply_schema, apply_views, reset_schema
from src.etl.transform import build_frames, issues_frame, summary_frame
from src.etl.validate import validate_all

logger = logging.getLogger(__name__)


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def run_pipeline(
    source: Path = RAW_DIR, report_dir: Path | None = REPORTS_DIR, reset: bool = False
) -> int:
    """Executa o pipeline e devolve o id da execução registrada em dq_execucao."""
    settings = load_settings()
    reference_date = settings.reference_date
    engine = get_engine(settings)

    if reset:
        reset_schema(engine)
    apply_schema(engine)
    apply_views(engine)

    execution_id = start_execution(engine, _display_path(source), reference_date)
    logger.info("Execution %d started (source: %s)", execution_id, _display_path(source))
    try:
        sources = extract_all(source)
        cities = read_cities()
        result = validate_all(sources, cities, reference_date)
        loaded_at = datetime.now().replace(microsecond=0)
        frames = build_frames(sources, result, cities, execution_id, reference_date, loaded_at)
        load_all(
            engine,
            execution_id,
            frames,
            summary_frame(result.summary, execution_id),
            issues_frame(result.issues, execution_id),
        )
    except Exception as error:
        fail_execution(engine, execution_id, error)
        logger.error("Execution %d failed: %s", execution_id, error)
        raise

    log_summary(result.summary)
    if report_dir is not None:
        write_reports(result, report_dir, reference_date, _display_path(source))
    logger.info("Execution %d finished", execution_id)
    return execution_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full data pipeline.")
    parser.add_argument("--source", type=Path, default=RAW_DIR)
    parser.add_argument("--reset-schema", action="store_true", help="drop and recreate the tables first")
    parser.add_argument("--no-report", action="store_true", help="do not write the quality report files")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run_pipeline(
        source=args.source,
        report_dir=None if args.no_report else REPORTS_DIR,
        reset=args.reset_schema,
    )


if __name__ == "__main__":
    main()