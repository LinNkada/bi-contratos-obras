"""Validação dos dados de origem (regras R01 a R23 do modelo de dados).

Cada função recebe a tabela como texto (como veio do CSV) e devolve os registros
aceitos, já convertidos para os tipos certos, e a lista de problemas encontrados.
Tratamento: "rejeita" tira o registro do fluxo; "alerta" só registra o problema.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from src.geo import haversine_km

REJECT = "rejeita"
ALERT = "alerta"
CASCADE = "CASCATA"

ISSUE_COLUMNS = ["tabela", "linha", "id_registro", "regra", "severidade", "detalhe"]

VALID_UFS = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})
VALID_REASONS = frozenset({"concluido", "cancelado_cliente", "rescindido"})
BRAZIL_LAT = (-34.0, 6.0)
BRAZIL_LON = (-74.0, -28.0)
MAX_CITY_DISTANCE_KM = 25.0

RULE_DESCRIPTIONS = {
    "R01": "cliente: id_cliente obrigatório e único",
    "R02": "cliente: nome_cliente obrigatório",
    "R03": "cliente: data_cadastro válida e não posterior à data de referência",
    "R04": "obra: id_obra obrigatório e único",
    "R05": "obra: id_cliente existe em cliente",
    "R06": "obra: nome_obra obrigatório",
    "R07": "obra: estado é uma UF válida",
    "R08": "obra: latitude e longitude presentes e dentro do Brasil",
    "R09": "obra: coordenadas a até 25 km do centro da cidade informada",
    "R10": "obra: qtd_portas é um inteiro maior que zero",
    "R11": "obra: tem ao menos um contrato válido",
    "R12": "contrato: id_contrato obrigatório e único",
    "R13": "contrato: id_obra existe em obra",
    "R14": "contrato: datas obrigatórias válidas",
    "R15": "contrato: data_fim_prevista_inicial não anterior a data_inicio",
    "R16": "contrato: data_fim_atual não anterior a data_fim_prevista_inicial",
    "R17": "contrato: data_retirada entre data_inicio e a data de referência",
    "R18": "contrato: motivo_encerramento preenchido se e somente se há data_retirada",
    "R19": "contrato: motivo_encerramento dentro do domínio permitido",
    "R20": "contrato: valor_mensal maior que zero",
    "R21": "contrato: data_inicio não posterior à data de referência",
    "R22": "contrato: data_inicio não anterior ao cadastro do cliente",
    "R23": "contrato: possível duplicidade (mesma obra, mesmo início e mesmo valor)",
    CASCADE: "registro rejeitado porque o registro pai (cliente ou obra) foi rejeitado",
}


@dataclass
class ValidationResult:
    valid: pd.DataFrame  # registros aceitos, com os tipos já convertidos
    issues: pd.DataFrame  # problemas encontrados (rejeições e alertas)
    received: int


@dataclass
class QualityResult:
    clientes: ValidationResult
    obras: ValidationResult
    contratos: ValidationResult
    issues: pd.DataFrame
    summary: pd.DataFrame


class IssueLog:
    """Acumula os problemas encontrados em uma tabela."""

    def __init__(self, table: str, ids: pd.Series) -> None:
        self.table = table
        self.ids = ids
        self.rows: list[dict] = []

    def add(self, mask: pd.Series, rule: str, severity: str, detail: str | pd.Series) -> None:
        for idx in mask.index[mask.to_numpy(dtype=bool)]:
            self.rows.append(
                {
                    "tabela": self.table,
                    "linha": int(idx) + 2,  # a linha 1 do CSV é o cabeçalho
                    "id_registro": self.ids.loc[idx],
                    "regra": rule,
                    "severidade": severity,
                    "detalhe": detail if isinstance(detail, str) else detail.loc[idx],
                }
            )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=ISSUE_COLUMNS)


def _parse_date(series: pd.Series) -> pd.Series:
    """Converte texto AAAA-MM-DD em data. Vazio ou inválido vira NaT."""
    return pd.to_datetime(series.str.strip(), format="%Y-%m-%d", errors="coerce")


def _finish(
    df: pd.DataFrame,
    log: IssueLog,
    parsed: dict[str, pd.Series],
    int_columns: tuple[str, ...] = (),
) -> ValidationResult:
    """Separa os registros aceitos dos rejeitados e aplica os tipos convertidos."""
    issues = log.to_frame()
    rejected = issues.loc[issues["severidade"] == REJECT, "linha"] - 2
    valid = df.copy()
    for column, series in parsed.items():
        valid[column] = series
    valid = valid.loc[~valid.index.isin(rejected.to_numpy())]
    for column in int_columns:
        valid[column] = valid[column].astype("int64")
    return ValidationResult(valid=valid, issues=issues, received=len(df))


# --------------------------------------------------------------------------
# Cliente (R01 a R03)
# --------------------------------------------------------------------------
def validate_clientes(df: pd.DataFrame, reference_date: date) -> ValidationResult:
    ids = df["id_cliente"].str.strip()
    log = IssueLog("cliente", ids)
    log.add(ids.eq(""), "R01", REJECT, "id_cliente vazio")
    log.add(ids.ne("") & ids.duplicated(keep="first"), "R01", REJECT, "id_cliente duplicado")
    log.add(df["nome_cliente"].str.strip().eq(""), "R02", REJECT, "nome_cliente vazio")

    registration = _parse_date(df["data_cadastro"])
    log.add(registration.isna(), "R03", REJECT, "data_cadastro vazia ou inválida")
    log.add(
        registration > pd.Timestamp(reference_date),
        "R03", REJECT, "data_cadastro posterior à data de referência",
    )
    return _finish(df, log, {"id_cliente": ids, "data_cadastro": registration})


# --------------------------------------------------------------------------
# Obra (R04 a R10)
# --------------------------------------------------------------------------
def validate_obras(
    df: pd.DataFrame,
    clientes_raw: pd.DataFrame,
    clientes: ValidationResult,
    cities: pd.DataFrame,
) -> ValidationResult:
    ids = df["id_obra"].str.strip()
    log = IssueLog("obra", ids)
    log.add(ids.eq(""), "R04", REJECT, "id_obra vazio")
    log.add(ids.ne("") & ids.duplicated(keep="first"), "R04", REJECT, "id_obra duplicado")

    # Pai inexistente (R05) é diferente de pai existente, mas rejeitado (CASCATA).
    client_ids = df["id_cliente"].str.strip()
    known_clients = set(clientes_raw["id_cliente"].str.strip()) - {""}
    valid_clients = set(clientes.valid["id_cliente"])
    log.add(~client_ids.isin(known_clients), "R05", REJECT, "id_cliente não existe em cliente")
    log.add(
        client_ids.isin(known_clients) & ~client_ids.isin(valid_clients),
        CASCADE, REJECT, "cliente rejeitado (registro pai rejeitado)",
    )

    name = df["nome_obra"].str.strip()
    log.add(name.eq(""), "R06", REJECT, "nome_obra vazio")

    state = df["estado"].str.strip()
    log.add(~state.isin(VALID_UFS), "R07", REJECT, "estado não é uma UF válida")

    lat = pd.to_numeric(df["latitude"].str.strip(), errors="coerce")
    lon = pd.to_numeric(df["longitude"].str.strip(), errors="coerce")
    coords_missing = lat.isna() | lon.isna()
    log.add(coords_missing, "R08", REJECT, "latitude ou longitude ausente ou inválida")
    in_brazil = lat.between(*BRAZIL_LAT) & lon.between(*BRAZIL_LON)
    log.add(~coords_missing & ~in_brazil, "R08", REJECT, "coordenadas fora do Brasil")

    # R09: distância até o centro da cidade informada (só para cidades da tabela de referência).
    city = df["cidade"].str.strip()
    centers = {
        (row.cidade, row.estado): (row.latitude, row.longitude)
        for row in cities.itertuples(index=False)
    }
    distances = pd.Series(float("nan"), index=df.index, dtype="float64")
    for idx in df.index[(~coords_missing & in_brazil).to_numpy(dtype=bool)]:
        center = centers.get((city.at[idx], state.at[idx]))
        if center is not None:
            distances.at[idx] = haversine_km(lat.at[idx], lon.at[idx], center[0], center[1])
    log.add(
        distances > MAX_CITY_DISTANCE_KM,
        "R09", ALERT,
        distances.map(lambda d: f"coordenadas a {d:.1f} km do centro da cidade informada"),
    )

    doors = pd.to_numeric(df["qtd_portas"].str.strip(), errors="coerce")
    invalid_doors = doors.isna() | (doors <= 0) | (doors % 1 != 0)
    log.add(invalid_doors, "R10", REJECT, "qtd_portas deve ser um inteiro maior que zero")

    parsed = {
        "id_obra": ids, "id_cliente": client_ids, "nome_obra": name, "cidade": city,
        "estado": state, "latitude": lat, "longitude": lon, "qtd_portas": doors,
    }
    return _finish(df, log, parsed, int_columns=("qtd_portas",))


# --------------------------------------------------------------------------
# Contrato (R12 a R23)
# --------------------------------------------------------------------------
def validate_contratos(
    df: pd.DataFrame,
    obras_raw: pd.DataFrame,
    obras: ValidationResult,
    clientes: ValidationResult,
    reference_date: date,
) -> ValidationResult:
    reference = pd.Timestamp(reference_date)
    ids = df["id_contrato"].str.strip()
    log = IssueLog("contrato", ids)
    duplicated_id = ids.ne("") & ids.duplicated(keep="first")
    log.add(ids.eq(""), "R12", REJECT, "id_contrato vazio")
    log.add(duplicated_id, "R12", REJECT, "id_contrato duplicado")

    work_ids = df["id_obra"].str.strip()
    known_works = set(obras_raw["id_obra"].str.strip()) - {""}
    valid_works = set(obras.valid["id_obra"])
    log.add(~work_ids.isin(known_works), "R13", REJECT, "id_obra não existe em obra")
    log.add(
        work_ids.isin(known_works) & ~work_ids.isin(valid_works),
        CASCADE, REJECT, "obra rejeitada (registro pai rejeitado)",
    )

    start = _parse_date(df["data_inicio"])
    initial_end = _parse_date(df["data_fim_prevista_inicial"])
    current_end = _parse_date(df["data_fim_atual"])
    required_dates = (
        ("data_inicio", start),
        ("data_fim_prevista_inicial", initial_end),
        ("data_fim_atual", current_end),
    )
    for column, parsed_date in required_dates:
        log.add(parsed_date.isna(), "R14", REJECT, f"{column} vazia ou inválida")
    log.add(initial_end < start, "R15", REJECT, "data_fim_prevista_inicial anterior a data_inicio")
    log.add(current_end < initial_end, "R16", REJECT, "data_fim_atual anterior a data_fim_prevista_inicial")

    removal_text = df["data_retirada"].str.strip()
    has_removal = removal_text.ne("")
    removal = _parse_date(removal_text)
    log.add(has_removal & removal.isna(), "R17", REJECT, "data_retirada inválida")
    log.add(removal < start, "R17", REJECT, "data_retirada anterior a data_inicio")
    log.add(removal > reference, "R17", REJECT, "data_retirada posterior à data de referência")

    reason = df["motivo_encerramento"].str.strip()
    has_reason = reason.ne("")
    log.add(
        has_removal & ~has_reason,
        "R18", REJECT, "motivo_encerramento vazio com data_retirada preenchida",
    )
    log.add(
        ~has_removal & has_reason,
        "R18", REJECT, "motivo_encerramento preenchido sem data_retirada",
    )
    log.add(
        has_reason & ~reason.isin(VALID_REASONS),
        "R19", REJECT, "motivo_encerramento fora do domínio permitido",
    )

    value = pd.to_numeric(df["valor_mensal"].str.strip(), errors="coerce")
    log.add(value.isna() | (value <= 0), "R20", REJECT, "valor_mensal ausente, inválido ou não positivo")
    log.add(start > reference, "R21", REJECT, "data_inicio posterior à data de referência")

    # R22 (alerta): início do contrato anterior ao cadastro do cliente da obra.
    work_to_client = dict(zip(obras.valid["id_obra"], obras.valid["id_cliente"]))
    registration_by_client = dict(zip(clientes.valid["id_cliente"], clientes.valid["data_cadastro"]))
    client_registration = pd.to_datetime(work_ids.map(work_to_client).map(registration_by_client))
    log.add(start < client_registration, "R22", ALERT, "data_inicio anterior ao cadastro do cliente")

    # R23 (alerta): mesma obra, mesmo início e mesmo valor que um contrato anterior.
    key = pd.DataFrame({"obra": work_ids, "inicio": start, "valor": value})
    possible_duplicate = key.notna().all(axis=1) & key.duplicated(keep="first") & ~duplicated_id
    log.add(
        possible_duplicate,
        "R23", ALERT, "possível duplicidade: mesma obra, mesmo início e mesmo valor",
    )

    parsed = {
        "id_contrato": ids, "id_obra": work_ids, "data_inicio": start,
        "data_fim_prevista_inicial": initial_end, "data_fim_atual": current_end,
        "data_retirada": removal, "motivo_encerramento": reason.mask(~has_reason),
        "valor_mensal": value,
    }
    return _finish(df, log, parsed)


def check_works_without_contracts(obras: ValidationResult, contratos: ValidationResult) -> pd.DataFrame:
    """R11 (alerta): obras aceitas que ficaram sem nenhum contrato aceito."""
    works = obras.valid
    has_contract = works["id_obra"].isin(set(contratos.valid["id_obra"]))
    log = IssueLog("obra", works["id_obra"])
    log.add(~has_contract, "R11", ALERT, "obra sem nenhum contrato válido")
    return log.to_frame()


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------
def build_summary(results: dict[str, ValidationResult], issues: pd.DataFrame) -> pd.DataFrame:
    """Recebidos, válidos, rejeitados e alertas por tabela (cada registro conta uma vez)."""
    rows = []
    for table, result in results.items():
        table_issues = issues[issues["tabela"] == table]
        rejected = set(table_issues.loc[table_issues["severidade"] == REJECT, "linha"])
        alerted = set(table_issues.loc[table_issues["severidade"] == ALERT, "linha"]) - rejected
        rows.append(
            {
                "tabela": table,
                "recebidos": result.received,
                "validos": result.received - len(rejected),
                "rejeitados": len(rejected),
                "alertas": len(alerted),
            }
        )
    return pd.DataFrame(rows)


def validate_all(
    sources: dict[str, pd.DataFrame], cities: pd.DataFrame, reference_date: date
) -> QualityResult:
    clientes = validate_clientes(sources["cliente"], reference_date)
    obras = validate_obras(sources["obra"], sources["cliente"], clientes, cities)
    contratos = validate_contratos(sources["contrato"], sources["obra"], obras, clientes, reference_date)
    works_without_contracts = check_works_without_contracts(obras, contratos)

    frames = [
        frame
        for frame in (clientes.issues, obras.issues, contratos.issues, works_without_contracts)
        if not frame.empty
    ]
    issues = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=ISSUE_COLUMNS)
    summary = build_summary(
        {"cliente": clientes, "obra": obras, "contrato": contratos}, issues
    )
    return QualityResult(clientes, obras, contratos, issues, summary)