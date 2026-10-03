from datetime import date

import pandas as pd
import pytest

from src.etl.extract import extract_all, read_cities
from src.etl.quality import format_report
from src.etl.validate import ALERT, CASCADE, REJECT, validate_all

REF = date(2026, 9, 30)

CITIES = pd.DataFrame(
    {
        "cidade": ["São Paulo", "Campinas"],
        "estado": ["SP", "SP"],
        "latitude": [-23.5505, -22.9056],
        "longitude": [-46.6333, -47.0608],
    }
)


def base_sources() -> dict[str, pd.DataFrame]:
    """Conjunto mínimo e válido: 2 clientes, 3 obras e 3 contratos."""
    clientes = pd.DataFrame(
        {
            "id_cliente": ["CLI-0001", "CLI-0002"],
            "nome_cliente": ["Construtora Aurora", "Incorporadora Delta"],
            "data_cadastro": ["2024-01-10", "2024-02-15"],
        }
    )
    obras = pd.DataFrame(
        {
            "id_obra": ["OBR-0001", "OBR-0002", "OBR-0003"],
            "id_cliente": ["CLI-0001", "CLI-0001", "CLI-0002"],
            "nome_obra": ["Edifício Jardins", "Torre Safira", "Residencial Coral"],
            "cidade": ["São Paulo", "São Paulo", "Campinas"],
            "estado": ["SP", "SP", "SP"],
            "latitude": ["-23.5505", "-23.5600", "-22.9056"],
            "longitude": ["-46.6333", "-46.6400", "-47.0608"],
            "qtd_portas": ["40", "25", "60"],
        }
    )
    contratos = pd.DataFrame(
        {
            "id_contrato": ["CTR-0001", "CTR-0002", "CTR-0003"],
            "id_obra": ["OBR-0001", "OBR-0002", "OBR-0003"],
            "data_inicio": ["2024-03-01", "2025-01-10", "2026-05-01"],
            "data_fim_prevista_inicial": ["2025-03-01", "2026-01-10", "2027-05-01"],
            "data_fim_atual": ["2025-06-01", "2026-01-10", "2027-05-01"],
            "data_retirada": ["2025-06-15", "", ""],
            "motivo_encerramento": ["concluido", "", ""],
            "valor_mensal": ["3400.00", "2100.50", "5100.00"],
        }
    )
    return {"cliente": clientes, "obra": obras, "contrato": contratos}


def with_change(table: str, row: int, column: str, value: str):
    sources = base_sources()
    sources[table].loc[row, column] = value
    return validate_all(sources, CITIES, REF)


def found(result) -> set[tuple[str, str, str]]:
    issues = result.issues
    return set(zip(issues["tabela"], issues["regra"], issues["severidade"]))


# (tabela, linha, coluna, novo valor, regra esperada, tratamento esperado)
CASES = [
    ("cliente", 0, "id_cliente", "", "R01", REJECT),
    ("cliente", 1, "id_cliente", "CLI-0001", "R01", REJECT),
    ("cliente", 0, "nome_cliente", "  ", "R02", REJECT),
    ("cliente", 0, "data_cadastro", "2024-02-30", "R03", REJECT),
    ("cliente", 0, "data_cadastro", "2026-10-15", "R03", REJECT),
    ("obra", 0, "id_obra", "", "R04", REJECT),
    ("obra", 1, "id_obra", "OBR-0001", "R04", REJECT),
    ("obra", 0, "id_cliente", "CLI-9999", "R05", REJECT),
    ("obra", 0, "nome_obra", "", "R06", REJECT),
    ("obra", 0, "estado", "XX", "R07", REJECT),
    ("obra", 0, "latitude", "", "R08", REJECT),
    ("obra", 0, "longitude", "10.0", "R08", REJECT),
    ("obra", 0, "latitude", "-22.9056", "R09", ALERT),
    ("obra", 0, "qtd_portas", "0", "R10", REJECT),
    ("obra", 0, "qtd_portas", "abc", "R10", REJECT),
    ("obra", 0, "qtd_portas", "4.5", "R10", REJECT),
    ("contrato", 0, "id_contrato", "", "R12", REJECT),
    ("contrato", 1, "id_contrato", "CTR-0001", "R12", REJECT),
    ("contrato", 0, "id_obra", "OBR-9999", "R13", REJECT),
    ("contrato", 0, "data_inicio", "31/03/2024", "R14", REJECT),
    ("contrato", 0, "data_fim_prevista_inicial", "2024-02-01", "R15", REJECT),
    ("contrato", 0, "data_fim_atual", "2025-01-01", "R16", REJECT),
    ("contrato", 0, "data_retirada", "2024-01-01", "R17", REJECT),
    ("contrato", 0, "data_retirada", "2026-12-01", "R17", REJECT),
    ("contrato", 0, "motivo_encerramento", "", "R18", REJECT),
    ("contrato", 1, "motivo_encerramento", "concluido", "R18", REJECT),
    ("contrato", 0, "motivo_encerramento", "cancelado", "R19", REJECT),
    ("contrato", 0, "valor_mensal", "0", "R20", REJECT),
    ("contrato", 0, "valor_mensal", "abc", "R20", REJECT),
    ("contrato", 2, "data_inicio", "2026-10-05", "R21", REJECT),
    ("contrato", 0, "data_inicio", "2024-01-05", "R22", ALERT),
]


def test_clean_sources_have_no_issues():
    result = validate_all(base_sources(), CITIES, REF)
    assert result.issues.empty
    assert (result.summary["rejeitados"] == 0).all()
    assert (result.summary["alertas"] == 0).all()


@pytest.mark.parametrize(
    "table,row,column,value,rule,severity",
    CASES,
    ids=[f"{case[4]}-{case[0]}.{case[2]}" for case in CASES],
)
def test_each_rule_is_triggered(table, row, column, value, rule, severity):
    result = with_change(table, row, column, value)
    assert (table, rule, severity) in found(result)


def test_possible_duplicate_contract_is_an_alert():
    sources = base_sources()
    sources["contrato"].loc[1, ["id_obra", "data_inicio", "valor_mensal"]] = [
        "OBR-0001", "2024-03-01", "3400.00",
    ]
    result = validate_all(sources, CITIES, REF)
    assert ("contrato", "R23", ALERT) in found(result)


def test_work_without_contract_is_an_alert():
    sources = base_sources()
    sources["contrato"] = sources["contrato"].iloc[:2].copy()
    result = validate_all(sources, CITIES, REF)
    assert ("obra", "R11", ALERT) in found(result)


def test_rejected_parent_rejects_children():
    result = with_change("cliente", 0, "nome_cliente", "")
    assert ("obra", CASCADE, REJECT) in found(result)
    assert ("contrato", CASCADE, REJECT) in found(result)
    summary = result.summary.set_index("tabela")
    assert summary.loc["cliente", "rejeitados"] == 1
    assert summary.loc["obra", "rejeitados"] == 2
    assert summary.loc["contrato", "rejeitados"] == 2


def test_summary_counts_each_record_once():
    sources = base_sources()
    sources["obra"].loc[0, ["nome_obra", "estado", "qtd_portas"]] = ["", "XX", "0"]
    result = validate_all(sources, CITIES, REF)
    summary = result.summary.set_index("tabela")
    assert summary.loc["obra", "rejeitados"] == 1
    assert summary.loc["obra", "validos"] == 2
    assert len(result.obras.valid) == 2


def test_valid_output_has_converted_types():
    result = validate_all(base_sources(), CITIES, REF)
    assert result.clientes.valid["data_cadastro"].dtype.kind == "M"
    assert result.contratos.valid["data_inicio"].dtype.kind == "M"
    assert result.contratos.valid["valor_mensal"].dtype.kind == "f"
    assert result.obras.valid["latitude"].dtype.kind == "f"
    assert result.obras.valid["qtd_portas"].dtype.kind == "i"


def test_report_lists_the_rules_found():
    result = with_change("obra", 0, "qtd_portas", "0")
    text = format_report(result, REF, "data/raw")
    assert "Resumo" in text
    assert "R10" in text


def test_generated_csvs_have_no_issues():
    result = validate_all(extract_all(), read_cities(), REF)
    assert result.issues.empty