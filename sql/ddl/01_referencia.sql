-- Tabelas de referência: cidades (macrorregião e coordenadas) e parâmetros do projeto.

CREATE TABLE IF NOT EXISTS ref_cidade (
    cidade       VARCHAR(80)  NOT NULL,
    estado       CHAR(2)      NOT NULL,
    macro_regiao VARCHAR(20)  NOT NULL,
    latitude     DECIMAL(9,6) NOT NULL COMMENT 'Centro da cidade',
    longitude    DECIMAL(9,6) NOT NULL COMMENT 'Centro da cidade',
    PRIMARY KEY (cidade, estado)
) COMMENT = 'Cidades de referência com macrorregião e coordenadas do centro';

CREATE TABLE IF NOT EXISTS ref_parametro (
    chave VARCHAR(50)  NOT NULL,
    valor VARCHAR(100) NOT NULL,
    PRIMARY KEY (chave)
) COMMENT = 'Parâmetros do projeto, como a data de referência';