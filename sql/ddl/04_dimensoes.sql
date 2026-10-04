-- Dimensões: só registros válidos, com tipos reais, chaves e restrições.

CREATE TABLE IF NOT EXISTS dim_calendario (
    data             DATE        NOT NULL,
    ano              SMALLINT    NOT NULL,
    trimestre        TINYINT     NOT NULL,
    mes              TINYINT     NOT NULL,
    nome_mes         VARCHAR(15) NOT NULL,
    ano_mes          CHAR(7)     NOT NULL COMMENT 'Formato AAAA-MM',
    primeiro_dia_mes DATE        NOT NULL,
    ultimo_dia_mes   DATE        NOT NULL,
    dia_mes          TINYINT     NOT NULL,
    dia_semana       TINYINT     NOT NULL COMMENT '1 = segunda-feira até 7 = domingo',
    nome_dia_semana  VARCHAR(20) NOT NULL,
    PRIMARY KEY (data)
) COMMENT = 'Calendário contínuo para análises por período';

CREATE TABLE IF NOT EXISTS dim_cliente (
    id_cliente    VARCHAR(20)  NOT NULL,
    nome_cliente  VARCHAR(120) NOT NULL,
    data_cadastro DATE         NOT NULL,
    PRIMARY KEY (id_cliente)
) COMMENT = 'Clientes válidos';

CREATE TABLE IF NOT EXISTS dim_obra (
    id_obra      VARCHAR(20)  NOT NULL,
    id_cliente   VARCHAR(20)  NOT NULL,
    nome_obra    VARCHAR(120) NOT NULL,
    cidade       VARCHAR(80)  NOT NULL,
    estado       CHAR(2)      NOT NULL,
    macro_regiao VARCHAR(20)  NULL COMMENT 'Vem de ref_cidade, vazio se a cidade não estiver na referência',
    latitude     DECIMAL(9,6) NOT NULL,
    longitude    DECIMAL(9,6) NOT NULL,
    qtd_portas   INT          NOT NULL,
    PRIMARY KEY (id_obra),
    KEY ix_obra_regiao (macro_regiao, estado),
    CONSTRAINT fk_obra_cliente FOREIGN KEY (id_cliente) REFERENCES dim_cliente (id_cliente),
    CONSTRAINT ck_obra_portas CHECK (qtd_portas > 0)
) COMMENT = 'Obras válidas';

CREATE TABLE IF NOT EXISTS dim_contrato (
    id_contrato               VARCHAR(20)   NOT NULL,
    id_obra                   VARCHAR(20)   NOT NULL,
    data_inicio               DATE          NOT NULL,
    data_fim_prevista_inicial DATE          NOT NULL,
    data_fim_atual            DATE          NOT NULL,
    data_retirada             DATE          NULL,
    motivo_encerramento       VARCHAR(20)   NULL,
    valor_mensal              DECIMAL(12,2) NOT NULL,
    status_contrato       VARCHAR(10) GENERATED ALWAYS AS (IF(data_retirada IS NULL, 'ativo', 'encerrado')) STORED
        COMMENT 'ativo se não há retirada',
    prorrogado            TINYINT(1)  GENERATED ALWAYS AS (data_fim_atual > data_fim_prevista_inicial) STORED
        COMMENT '1 se o prazo atual é maior que o prazo assinado',
    dias_prorrogados      INT         GENERATED ALWAYS AS (DATEDIFF(data_fim_atual, data_fim_prevista_inicial)) STORED,
    duracao_prevista_dias INT         GENERATED ALWAYS AS (DATEDIFF(data_fim_prevista_inicial, data_inicio)) STORED,
    duracao_real_dias     INT         GENERATED ALWAYS AS (DATEDIFF(data_retirada, data_inicio)) STORED
        COMMENT 'Vazio enquanto a proteção está instalada',
    desvio_prazo_dias     INT         GENERATED ALWAYS AS (DATEDIFF(data_retirada, data_fim_prevista_inicial)) STORED
        COMMENT 'Retirada real menos o prazo assinado, vazio enquanto instalada',
    PRIMARY KEY (id_contrato),
    KEY ix_contrato_obra (id_obra),
    KEY ix_contrato_inicio (data_inicio),
    KEY ix_contrato_fim_atual (data_fim_atual),
    KEY ix_contrato_retirada (data_retirada),
    CONSTRAINT fk_contrato_obra FOREIGN KEY (id_obra) REFERENCES dim_obra (id_obra),
    CONSTRAINT ck_contrato_valor CHECK (valor_mensal > 0),
    CONSTRAINT ck_contrato_prazos CHECK (
        data_fim_prevista_inicial >= data_inicio AND data_fim_atual >= data_fim_prevista_inicial
    ),
    CONSTRAINT ck_contrato_retirada CHECK (data_retirada IS NULL OR data_retirada >= data_inicio),
    CONSTRAINT ck_contrato_motivo CHECK (
        motivo_encerramento IS NULL OR motivo_encerramento IN ('concluido', 'cancelado_cliente', 'rescindido')
    ),
    CONSTRAINT ck_contrato_retirada_motivo CHECK ((data_retirada IS NULL) = (motivo_encerramento IS NULL))
) COMMENT = 'Contratos válidos, com colunas calculadas pelo banco';