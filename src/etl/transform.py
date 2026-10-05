"""Transformação: prepara os dados validados para gravar nas tabelas do banco."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from src.etl.validate import QualityResult

MONTH_NAMES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
WEEKDAY_NAMES = (
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
)


def staging_frame(source: pd.DataFrame, execution_id: int, loaded_at: datetime) -> pd.DataFrame:
    """Cópia fiel do CSV (tudo texto), com a linha de origem e os dados da execução."""
    frame = source.copy()
    frame.insert(0, "linha", frame.index + 2)  # a linha 1 do CSV é o cabeçalho
    frame["id_execucao"] = execution_id
    frame["carregado_em"] = loaded_at
    return frame


def dim_cliente_frame(valid: pd.DataFrame) -> pd.DataFrame:
    frame = valid[["id_cliente", "nome_cliente", "data_cadastro"]].copy()
    frame["data_cadastro"] = frame["data_cadastro"].dt.date
    return frame


def dim_obra_frame(valid: pd.DataFrame, cities: pd.DataFrame) -> pd.DataFrame:
    """Obras válidas, com a macrorregião vinda da tabela de cidades (vazia se não houver)."""
    lookup = {
        (row.cidade, row.estado): row.macro_regiao for row in cities.itertuples(index=False)
    }
    frame = valid[
        ["id_obra", "id_cliente", "nome_obra", "cidade", "estado",
         "latitude", "longitude", "qtd_portas"]
    ].copy()
    frame["macro_regiao"] = [lookup.get(key) for key in zip(frame["cidade"], frame["estado"])]
    return frame


def dim_contrato_frame(valid: pd.DataFrame) -> pd.DataFrame:
    """Só as colunas-base: as calculadas (status, prorrogado...) são geradas pelo MySQL."""
    frame = valid[
        ["id_contrato", "id_obra", "data_inicio", "data_fim_prevista_inicial",
         "data_fim_atual", "data_retirada", "motivo_encerramento", "valor_mensal"]
    ].copy()
    for column in ("data_inicio", "data_fim_prevista_inicial", "data_fim_atual", "data_retirada"):
        frame[column] = frame[column].dt.date
    return frame


def build_calendar(start: date, end: date) -> pd.DataFrame:
    """Calendário contínuo, um registro por dia, com nomes em português."""
    days = pd.date_range(start, end, freq="D")
    frame = pd.DataFrame({"data": days})
    frame["ano"] = days.year
    frame["trimestre"] = days.quarter
    frame["mes"] = days.month
    frame["nome_mes"] = [MONTH_NAMES[month - 1] for month in days.month]
    frame["ano_mes"] = days.strftime("%Y-%m")
    frame["primeiro_dia_mes"] = days.to_period("M").to_timestamp()
    frame["ultimo_dia_mes"] = days + pd.offsets.MonthEnd(0)
    frame["dia_mes"] = days.day
    frame["dia_semana"] = days.dayofweek + 1  # 1 = segunda-feira
    frame["nome_dia_semana"] = [WEEKDAY_NAMES[day] for day in days.dayofweek]
    for column in ("data", "primeiro_dia_mes", "ultimo_dia_mes"):
        frame[column] = frame[column].dt.date
    return frame


def calendar_bounds(
    clientes_valid: pd.DataFrame, contratos_valid: pd.DataFrame, reference_date: date
) -> tuple[date, date]:
    """Do início do primeiro ano com dados ao fim do ano seguinte à data de referência."""
    dates = pd.concat(
        [
            clientes_valid["data_cadastro"],
            contratos_valid["data_inicio"],
            contratos_valid["data_fim_prevista_inicial"],
            contratos_valid["data_fim_atual"],
            contratos_valid["data_retirada"],
        ]
    ).dropna()
    reference = pd.Timestamp(reference_date)
    first = min(dates.min(), reference) if not dates.empty else reference
    last = max(dates.max(), reference) if not dates.empty else reference
    return date(first.year, 1, 1), date(max(last.year, reference_date.year + 1), 12, 31)


def ref_cidade_frame(cities: pd.DataFrame) -> pd.DataFrame:
    return cities[["cidade", "estado", "macro_regiao", "latitude", "longitude"]].copy()


def ref_parametro_frame(reference_date: date) -> pd.DataFrame:
    return pd.DataFrame({"chave": ["data_referencia"], "valor": [reference_date.isoformat()]})


def summary_frame(summary: pd.DataFrame, execution_id: int) -> pd.DataFrame:
    frame = summary.rename(
        columns={
            "recebidos": "registros_recebidos",
            "validos": "registros_validos",
            "rejeitados": "registros_rejeitados",
            "alertas": "registros_com_alerta",
        }
    )
    frame.insert(0, "id_execucao", execution_id)
    return frame


def issues_frame(issues: pd.DataFrame, execution_id: int) -> pd.DataFrame:
    frame = issues[["tabela", "linha", "id_registro", "regra", "severidade", "detalhe"]].copy()
    frame.insert(0, "id_execucao", execution_id)
    return frame


def build_frames(
    sources: dict[str, pd.DataFrame],
    result: QualityResult,
    cities: pd.DataFrame,
    execution_id: int,
    reference_date: date,
    loaded_at: datetime,
) -> dict[str, pd.DataFrame]:
    """Tudo que será gravado, por nome de tabela."""
    clientes = result.clientes.valid
    obras = result.obras.valid
    contratos = result.contratos.valid
    start, end = calendar_bounds(clientes, contratos, reference_date)
    return {
        "ref_cidade": ref_cidade_frame(cities),
        "ref_parametro": ref_parametro_frame(reference_date),
        "stg_cliente": staging_frame(sources["cliente"], execution_id, loaded_at),
        "stg_obra": staging_frame(sources["obra"], execution_id, loaded_at),
        "stg_contrato": staging_frame(sources["contrato"], execution_id, loaded_at),
        "dim_calendario": build_calendar(start, end),
        "dim_cliente": dim_cliente_frame(clientes),
        "dim_obra": dim_obra_frame(obras, cities),
        "dim_contrato": dim_contrato_frame(contratos),
    }