-- Histórico de qualidade dos dados: uma linha por execução do pipeline,
-- totais por tabela e cada problema encontrado (rejeições e alertas).

CREATE TABLE IF NOT EXISTS dq_execucao (
    id_execucao     INT          NOT NULL AUTO_INCREMENT,
    iniciada_em     DATETIME     NOT NULL,
    finalizada_em   DATETIME     NULL,
    origem          VARCHAR(255) NOT NULL COMMENT 'Pasta dos CSVs processados',
    data_referencia DATE         NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'em_andamento',
    mensagem        VARCHAR(500) NULL COMMENT 'Motivo da falha, quando houver',
    PRIMARY KEY (id_execucao),
    CONSTRAINT ck_execucao_status CHECK (status IN ('em_andamento', 'concluida', 'falhou'))
) COMMENT = 'Uma linha por execução do pipeline';

CREATE TABLE IF NOT EXISTS dq_resumo (
    id_execucao          INT         NOT NULL,
    tabela               VARCHAR(30) NOT NULL,
    registros_recebidos  INT         NOT NULL,
    registros_validos    INT         NOT NULL,
    registros_rejeitados INT         NOT NULL,
    registros_com_alerta INT         NOT NULL,
    PRIMARY KEY (id_execucao, tabela),
    CONSTRAINT fk_resumo_execucao FOREIGN KEY (id_execucao) REFERENCES dq_execucao (id_execucao)
) COMMENT = 'Totais de recebidos, válidos, rejeitados e alertas por tabela e execução';

CREATE TABLE IF NOT EXISTS dq_problema (
    id_problema BIGINT       NOT NULL AUTO_INCREMENT,
    id_execucao INT          NOT NULL,
    tabela      VARCHAR(30)  NOT NULL,
    linha       INT          NOT NULL COMMENT 'Linha do CSV de origem (o cabeçalho é a linha 1)',
    id_registro VARCHAR(255) NULL,
    regra       VARCHAR(20)  NOT NULL,
    severidade  VARCHAR(10)  NOT NULL,
    detalhe     VARCHAR(500) NULL,
    PRIMARY KEY (id_problema),
    KEY ix_problema_execucao (id_execucao, tabela, linha),
    CONSTRAINT fk_problema_execucao FOREIGN KEY (id_execucao) REFERENCES dq_execucao (id_execucao),
    CONSTRAINT ck_problema_severidade CHECK (severidade IN ('rejeita', 'alerta'))
) COMMENT = 'Cada problema encontrado na validação, com a regra violada';