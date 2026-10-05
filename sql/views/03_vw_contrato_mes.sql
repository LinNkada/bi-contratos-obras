-- vw_contrato_mes: um registro por contrato por mês em que a proteção esteve instalada,
-- até a data de referência. É a tabela de fatos do Power BI.
-- Receita do mês = valor_mensal x dias ativos no mês / dias do mês.

CREATE OR REPLACE VIEW vw_contrato_mes AS
WITH parametro AS (
    SELECT CAST(valor AS DATE) AS data_referencia
    FROM ref_parametro
    WHERE chave = 'data_referencia'
),
meses AS (
    SELECT
        cal.primeiro_dia_mes,
        cal.ultimo_dia_mes,
        cal.ano_mes,
        LEAST(cal.ultimo_dia_mes, p.data_referencia) AS fim_periodo
    FROM dim_calendario AS cal
    CROSS JOIN parametro AS p
    WHERE cal.data = cal.primeiro_dia_mes
      AND cal.primeiro_dia_mes <= p.data_referencia
),
base AS (
    SELECT
        d.id_contrato,
        d.id_obra,
        o.id_cliente,
        d.valor_mensal,
        m.primeiro_dia_mes AS mes,
        m.ultimo_dia_mes,
        m.ano_mes,
        DATEDIFF(
            LEAST(COALESCE(d.data_retirada, p.data_referencia), m.fim_periodo),
            GREATEST(d.data_inicio, m.primeiro_dia_mes)
        ) + 1 AS dias_ativos,
        CASE WHEN d.data_inicio < m.primeiro_dia_mes THEN 1 ELSE 0 END AS ativo_no_inicio_mes,
        CASE WHEN d.data_inicio BETWEEN m.primeiro_dia_mes AND m.fim_periodo THEN 1 ELSE 0 END AS iniciou_no_mes,
        CASE WHEN d.data_retirada BETWEEN m.primeiro_dia_mes AND m.fim_periodo THEN 1 ELSE 0 END AS retirado_no_mes,
        CASE
            WHEN d.data_retirada BETWEEN m.primeiro_dia_mes AND m.fim_periodo
             AND d.motivo_encerramento IN ('cancelado_cliente', 'rescindido')
            THEN 1 ELSE 0
        END AS perdido_no_mes,
        CASE
            WHEN d.data_inicio <= m.fim_periodo
             AND (d.data_retirada IS NULL OR d.data_retirada > m.fim_periodo)
            THEN 1 ELSE 0
        END AS ativo_no_fim_mes
    FROM dim_contrato AS d
    JOIN dim_obra AS o ON o.id_obra = d.id_obra
    CROSS JOIN parametro AS p
    JOIN meses AS m
      ON d.data_inicio <= m.fim_periodo
     AND COALESCE(d.data_retirada, p.data_referencia) >= m.primeiro_dia_mes
)
SELECT
    id_contrato,
    id_obra,
    id_cliente,
    mes,
    ano_mes,
    valor_mensal,
    dias_ativos,
    ROUND(valor_mensal * dias_ativos / DAY(ultimo_dia_mes), 2) AS receita_mes,
    ativo_no_inicio_mes,
    iniciou_no_mes,
    retirado_no_mes,
    perdido_no_mes,
    ativo_no_fim_mes,
    valor_mensal * ativo_no_inicio_mes AS carteira_inicio_mes,
    valor_mensal * ativo_no_fim_mes AS carteira_fim_mes,
    valor_mensal * perdido_no_mes AS valor_perdido_mes
FROM base;