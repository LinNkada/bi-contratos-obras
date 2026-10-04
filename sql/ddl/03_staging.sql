-- Staging: cópia fiel dos CSVs, tudo como texto, com a linha de origem.
-- É substituída a cada execução do pipeline.

CREATE TABLE IF NOT EXISTS stg_cliente (
    linha         INT          NOT NULL COMMENT 'Linha do CSV de origem (o cabeçalho é a linha 1)',
    id_cliente    VARCHAR(255) NULL,
    nome_cliente  VARCHAR(255) NULL,
    data_cadastro VARCHAR(255) NULL,
    id_execucao   INT          NOT NULL,
    carregado_em  DATETIME     NOT NULL,
    PRIMARY KEY (linha),
    CONSTRAINT fk_stg_cliente_execucao FOREIGN KEY (id_execucao) REFERENCES dq_execucao (id_execucao)
) COMMENT = 'Cópia fiel de cliente.csv';

CREATE TABLE IF NOT EXISTS stg_obra (
    linha        INT          NOT NULL COMMENT 'Linha do CSV de origem (o cabeçalho é a linha 1)',
    id_obra      VARCHAR(255) NULL,
    id_cliente   VARCHAR(255) NULL,
    nome_obra    VARCHAR(255) NULL,
    cidade       VARCHAR(255) NULL,
    estado       VARCHAR(255) NULL,
    latitude     VARCHAR(255) NULL,
    longitude    VARCHAR(255) NULL,
    qtd_portas   VARCHAR(255) NULL,
    id_execucao  INT          NOT NULL,
    carregado_em DATETIME     NOT NULL,
    PRIMARY KEY (linha),
    CONSTRAINT fk_stg_obra_execucao FOREIGN KEY (id_execucao) REFERENCES dq_execucao (id_execucao)
) COMMENT = 'Cópia fiel de obra.csv';

CREATE TABLE IF NOT EXISTS stg_contrato (
    linha                     INT          NOT NULL COMMENT 'Linha do CSV de origem (o cabeçalho é a linha 1)',
    id_contrato               VARCHAR(255) NULL,
    id_obra                   VARCHAR(255) NULL,
    data_inicio               VARCHAR(255) NULL,
    data_fim_prevista_inicial VARCHAR(255) NULL,
    data_fim_atual            VARCHAR(255) NULL,
    data_retirada             VARCHAR(255) NULL,
    motivo_encerramento       VARCHAR(255) NULL,
    valor_mensal              VARCHAR(255) NULL,
    id_execucao               INT          NOT NULL,
    carregado_em              DATETIME     NOT NULL,
    PRIMARY KEY (linha),
    CONSTRAINT fk_stg_contrato_execucao FOREIGN KEY (id_execucao) REFERENCES dq_execucao (id_execucao)
) COMMENT = 'Cópia fiel de contrato.csv';