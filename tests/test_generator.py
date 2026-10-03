import pandas as pd
import pytest

from src.geo import haversine_km
from src.synthetic.generator import generate_dataset, load_cities
from src.synthetic.params import SyntheticParams

SMALL = SyntheticParams(n_clients=10, n_works=25)
MOTIVOS = {"concluido", "cancelado_cliente", "rescindido"}


@pytest.fixture(scope="module")
def dataset():
    return generate_dataset(SMALL)


def test_same_seed_generates_same_data(dataset):
    again = generate_dataset(SMALL)
    for name, df in dataset.items():
        pd.testing.assert_frame_equal(df, again[name])


def test_ids_are_unique(dataset):
    assert dataset["cliente"]["id_cliente"].is_unique
    assert dataset["obra"]["id_obra"].is_unique
    assert dataset["contrato"]["id_contrato"].is_unique


def test_foreign_keys_exist(dataset):
    clientes = set(dataset["cliente"]["id_cliente"])
    obras = set(dataset["obra"]["id_obra"])
    assert set(dataset["obra"]["id_cliente"]) <= clientes
    assert set(dataset["contrato"]["id_obra"]) <= obras


def test_every_work_has_a_contract(dataset):
    assert set(dataset["obra"]["id_obra"]) == set(dataset["contrato"]["id_obra"])


def test_every_client_has_a_work(dataset):
    assert set(dataset["cliente"]["id_cliente"]) == set(dataset["obra"]["id_cliente"])


def test_contract_date_rules(dataset):
    c = dataset["contrato"]
    assert (c["data_fim_prevista_inicial"] >= c["data_inicio"]).all()
    assert (c["data_fim_atual"] >= c["data_fim_prevista_inicial"]).all()
    assert (c["data_inicio"] <= SMALL.reference_date).all()
    retired = c[c["data_retirada"].notna()]
    assert (retired["data_retirada"] >= retired["data_inicio"]).all()
    assert (retired["data_retirada"] <= SMALL.reference_date).all()


def test_reason_exists_only_when_retired(dataset):
    c = dataset["contrato"]
    has_reason = c["motivo_encerramento"].notna().to_numpy()
    is_retired = c["data_retirada"].notna().to_numpy()
    assert (has_reason == is_retired).all()


def test_reason_is_in_allowed_domain(dataset):
    reasons = set(dataset["contrato"]["motivo_encerramento"].dropna())
    assert reasons <= MOTIVOS


def test_values_are_positive(dataset):
    assert (dataset["contrato"]["valor_mensal"] > 0).all()
    assert (dataset["obra"]["qtd_portas"] > 0).all()


def test_coordinates_are_close_to_the_city(dataset):
    cities = load_cities().set_index(["cidade", "estado"])
    for obra in dataset["obra"].itertuples(index=False):
        city = cities.loc[(obra.cidade, obra.estado)]
        distance = haversine_km(
            obra.latitude, obra.longitude, city["latitude"], city["longitude"]
        )
        assert distance <= 25


def test_client_registered_before_first_contract(dataset):
    merged = (
        dataset["contrato"]
        .merge(dataset["obra"][["id_obra", "id_cliente"]], on="id_obra")
        .merge(dataset["cliente"], on="id_cliente")
    )
    assert (merged["data_cadastro"] <= merged["data_inicio"]).all()


def test_default_scenario_shape():
    data = generate_dataset()
    contracts = data["contrato"]
    ended = contracts[contracts["data_retirada"].notna()]
    active = contracts[contracts["data_retirada"].isna()]

    assert len(data["cliente"]) == 40
    assert len(data["obra"]) == 100
    assert 120 <= len(contracts) <= 190
    assert len(ended) > 0 and len(active) > 0
    extended_share = (ended["data_fim_atual"] > ended["data_fim_prevista_inicial"]).mean()
    assert 0.3 <= extended_share <= 0.95

def test_monthly_value_has_a_sensible_minimum(dataset):
    assert (dataset["contrato"]["valor_mensal"] >= 100).all()