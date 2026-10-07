import os

import pytest

from src.db import get_engine
from src.etl.extract import extract_all, read_cities
from src.etl.reconcile import (
    compare_kpis,
    compare_monthly,
    kpis_from_pandas,
    kpis_from_sql,
    monthly_from_pandas,
    monthly_from_sql,
    read_reference_date,
)
from src.etl.indicators import expiry_indicators_from_pandas, expiry_indicators_from_sql
from src.etl.validate import validate_all
from src.pipeline import run_pipeline
from src.etl.indicators import rehire_indicators_from_pandas, rehire_indicators_from_sql
from src.etl.monthly_kpis import compare_monthly_kpis, monthly_kpis_from_pandas, monthly_kpis_from_sql

requires_db = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="defina RUN_DB_TESTS=1 para testar contra o MySQL",
)


@requires_db
def test_views_agree_with_the_independent_pandas_calculation():
    run_pipeline(report_dir=None)
    engine = get_engine()
    reference_date = read_reference_date(engine)
    result = validate_all(extract_all(), read_cities(), reference_date)
    obras, contratos = result.obras.valid, result.contratos.valid

    monthly = monthly_from_pandas(contratos, reference_date)
    differences = compare_monthly(monthly, monthly_from_sql(engine))
    kpis = compare_kpis(kpis_from_pandas(obras, contratos, monthly, reference_date), kpis_from_sql(engine))

    assert differences.empty, differences.head(10).to_string()
    assert kpis["ok"].all(), kpis.to_string()

@requires_db
def test_expiry_indicators_agree_between_sql_and_pandas():
    run_pipeline(report_dir=None)
    engine = get_engine()
    reference_date = read_reference_date(engine)
    result = validate_all(extract_all(), read_cities(), reference_date)

    expected = expiry_indicators_from_pandas(result.obras.valid, result.contratos.valid, reference_date)
    actual = expiry_indicators_from_sql(engine)
    kpis = compare_kpis(expected, actual)
    assert kpis["ok"].all(), kpis.to_string()

@requires_db
def test_monthly_kpis_and_rehire_agree_between_sql_and_pandas():
    run_pipeline(report_dir=None)
    engine = get_engine()
    reference_date = read_reference_date(engine)
    result = validate_all(extract_all(), read_cities(), reference_date)
    obras, contratos = result.obras.valid, result.contratos.valid

    monthly = monthly_from_pandas(contratos, reference_date)
    differences = compare_monthly_kpis(
        monthly_kpis_from_pandas(monthly, reference_date), monthly_kpis_from_sql(engine)
    )
    assert differences.empty, differences.head(10).to_string()

    kpis = compare_kpis(
        rehire_indicators_from_pandas(obras, contratos, reference_date),
        rehire_indicators_from_sql(engine),
    )
    assert kpis["ok"].all(), kpis.to_string()