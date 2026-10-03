from datetime import date

import pandas as pd

from src.etl.extract import extract_all, read_cities
from src.etl.validate import REJECT, validate_all
from src.synthetic.inject_errors import inject_errors

REF = date(2026, 9, 30)
ALL_RULES = {f"R{i:02d}" for i in range(1, 24)} | {"CASCATA"}


def _run():
    clean = extract_all()
    dirty, manifest = inject_errors(clean, REF)
    result = validate_all(dirty, read_cities(), REF)
    return clean, dirty, manifest, result


def test_validator_finds_every_injected_error():
    _, _, manifest, result = _run()
    detected: dict[tuple[str, int], set[str]] = {}
    for row in result.issues.itertuples(index=False):
        detected.setdefault((row.tabela, row.linha), set()).add(row.regra)

    missing = []
    for row in manifest.itertuples(index=False):
        expected = set(row.regras_esperadas.split(","))
        found = detected.get((row.tabela, row.linha), set())
        if not expected <= found:
            missing.append((row.tabela, row.linha, sorted(expected - found)))
    assert not missing, f"Injected errors not detected: {missing}"


def test_nothing_is_rejected_beyond_the_injected_errors():
    _, _, manifest, result = _run()
    rejected = {
        (row.tabela, row.linha)
        for row in result.issues.itertuples(index=False)
        if row.severidade == REJECT
    }
    injected = {(row.tabela, row.linha) for row in manifest.itertuples(index=False)}
    assert rejected <= injected


def test_manifest_covers_every_rule():
    _, _, manifest, _ = _run()
    covered = {rule for text in manifest["regras_esperadas"] for rule in text.split(",")}
    assert covered == ALL_RULES


def test_injection_is_deterministic():
    clean = extract_all()
    first_tables, first_manifest = inject_errors(clean, REF, seed=7)
    second_tables, second_manifest = inject_errors(clean, REF, seed=7)
    for name in first_tables:
        pd.testing.assert_frame_equal(first_tables[name], second_tables[name])
    pd.testing.assert_frame_equal(first_manifest, second_manifest)


def test_clean_input_is_not_modified():
    clean = extract_all()
    before = {name: df.copy() for name, df in clean.items()}
    inject_errors(clean, REF)
    for name in clean:
        pd.testing.assert_frame_equal(clean[name], before[name])