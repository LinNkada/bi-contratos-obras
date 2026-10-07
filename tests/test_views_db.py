import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from src.db import get_engine
from src.pipeline import run_pipeline

requires_db = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="defina RUN_DB_TESTS=1 para testar contra o MySQL",
)


def _insert_test_data(conn) -> None:
    conn.execute(text("INSERT INTO dim_cliente VALUES ('CLI-T', 'Cliente Teste', '2024-01-10')"))
    conn.execute(
        text(
            "INSERT INTO dim_obra (id_obra, id_cliente, nome_obra, cidade, estado, macro_regiao, "
            "latitude, longitude, qtd_portas) VALUES ('OBR-T', 'CLI-T', 'Obra Teste', "
            "'São Paulo', 'SP', 'Sudeste', -23.5505, -46.6333, 40)"
        )
    )
    columns = (
        "(id_contrato, id_obra, data_inicio, data_fim_prevista_inicial, data_fim_atual, "
        "data_retirada, motivo_encerramento, valor_mensal)"
    )
    # Exemplo do glossário: 16/03 a 10/06, concluído, valor 10.000,00.
    conn.execute(
        text(
            f"INSERT INTO dim_contrato {columns} VALUES ('CTR-T', 'OBR-T', '2026-03-16', "
            "'2026-06-16', '2026-06-16', '2026-06-10', 'concluido', 10000.00)"
        )
    )
    # Contrato cancelado em 20/06: conta como perda em junho.
    conn.execute(
        text(
            f"INSERT INTO dim_contrato {columns} VALUES ('CTR-U', 'OBR-T', '2026-01-05', "
            "'2026-12-05', '2026-12-05', '2026-06-20', 'cancelado_cliente', 5000.00)"
        )
    )


@requires_db
def test_monthly_view_reproduces_the_glossary_example():
    run_pipeline(report_dir=None)  # garante que a data de referência e o calendário estão carregados
    engine = get_engine()
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            _insert_test_data(conn)
            rows = conn.execute(
                text(
                    "SELECT ano_mes, dias_ativos, receita_mes, ativo_no_inicio_mes, iniciou_no_mes, "
                    "retirado_no_mes, ativo_no_fim_mes FROM vw_contrato_mes "
                    "WHERE id_contrato = 'CTR-T' ORDER BY mes"
                )
            ).fetchall()
            june_loss = conn.execute(
                text(
                    "SELECT perdido_no_mes, valor_perdido_mes, ativo_no_inicio_mes "
                    "FROM vw_contrato_mes WHERE id_contrato = 'CTR-U' AND ano_mes = '2026-06'"
                )
            ).one()
        finally:
            transaction.rollback()

    assert [(r.ano_mes, r.dias_ativos, r.receita_mes) for r in rows] == [
        ("2026-03", 16, Decimal("5161.29")),
        ("2026-04", 30, Decimal("10000.00")),
        ("2026-05", 31, Decimal("10000.00")),
        ("2026-06", 10, Decimal("3333.33")),
    ]
    assert sum(r.receita_mes for r in rows) == Decimal("28494.62")

    first, last = rows[0], rows[-1]
    assert (first.ativo_no_inicio_mes, first.iniciou_no_mes, first.ativo_no_fim_mes) == (0, 1, 1)
    assert (last.ativo_no_inicio_mes, last.retirado_no_mes, last.ativo_no_fim_mes) == (1, 1, 0)
    assert june_loss.perdido_no_mes == 1
    assert june_loss.valor_perdido_mes == Decimal("5000.00")
    assert june_loss.ativo_no_inicio_mes == 1

@requires_db
def test_expiry_view_bands_and_continuity():
    run_pipeline(report_dir=None)  # garante a data de referência 2026-09-30
    engine = get_engine()
    # (contrato, cliente, data_fim_atual, faixa esperada, continuidade, em risco)
    cases = [
        ("CTR-TA", "T1", "2026-10-20", "0-30", 1, 0),   # o cliente T1 tem o CTR-TB até 2027
        ("CTR-TB", "T1", "2027-04-18", "mais_de_90", 0, 0),
        ("CTR-TC", "T2", "2026-11-14", "31-60", 0, 1),
        ("CTR-TD", "T3", "2026-09-20", "vencido_em_aberto", 0, 0),
        ("CTR-TE", "T4", "2026-09-30", "0-30", 0, 1),   # vence na própria data de referência
        ("CTR-TF", "T5", "2026-10-30", "0-30", 0, 1),   # 30 dias
        ("CTR-TG", "T6", "2026-10-31", "31-60", 0, 1),  # 31 dias
        ("CTR-TH", "T7", "2026-12-29", "61-90", 0, 1),  # 90 dias
        ("CTR-TI", "T8", "2026-12-30", "mais_de_90", 0, 0),  # 91 dias
    ]
    contract_columns = (
        "(id_contrato, id_obra, data_inicio, data_fim_prevista_inicial, data_fim_atual, "
        "data_retirada, motivo_encerramento, valor_mensal)"
    )
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            for client in sorted({case[1] for case in cases}):
                conn.execute(
                    text(f"INSERT INTO dim_cliente VALUES ('CLI-{client}', 'Cliente {client}', '2024-01-10')")
                )
                conn.execute(
                    text(
                        "INSERT INTO dim_obra (id_obra, id_cliente, nome_obra, cidade, estado, macro_regiao, "
                        f"latitude, longitude, qtd_portas) VALUES ('OBR-{client}', 'CLI-{client}', "
                        "'Obra Teste', 'São Paulo', 'SP', 'Sudeste', -23.5505, -46.6333, 40)"
                    )
                )
            for contract, client, end_date, *_ in cases:
                conn.execute(
                    text(
                        f"INSERT INTO dim_contrato {contract_columns} VALUES ('{contract}', "
                        f"'OBR-{client}', '2026-01-10', '2026-02-10', '{end_date}', NULL, NULL, 1000.00)"
                    )
                )
            rows = conn.execute(
                text(
                    "SELECT id_contrato, faixa_vencimento, cliente_com_continuidade, em_risco "
                    "FROM vw_vencimento WHERE id_contrato LIKE 'CTR-T_' ORDER BY id_contrato"
                )
            ).fetchall()
        finally:
            transaction.rollback()

    found = {r.id_contrato: (r.faixa_vencimento, r.cliente_com_continuidade, r.em_risco) for r in rows}
    expected = {case[0]: (case[3], case[4], case[5]) for case in cases}
    assert found == expected