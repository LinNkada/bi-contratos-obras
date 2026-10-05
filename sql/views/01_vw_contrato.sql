-- vw_contrato: um registro por contrato, com cliente e obra, e os indicadores
-- que dependem da data de referência (vencido em aberto e dias para o vencimento).

CREATE OR REPLACE VIEW vw_contrato AS
SELECT
    c.id_contrato,
    c.id_obra,
    o.id_cliente,
    cl.nome_cliente,
    o.nome_obra,
    o.cidade,
    o.estado,
    o.macro_regiao,
    o.latitude,
    o.longitude,
    o.qtd_portas,
    c.data_inicio,
    c.data_fim_prevista_inicial,
    c.data_fim_atual,
    c.data_retirada,
    c.motivo_encerramento,
    c.valor_mensal,
    c.status_contrato,
    c.prorrogado,
    c.dias_prorrogados,
    c.duracao_prevista_dias,
    c.duracao_real_dias,
    c.desvio_prazo_dias,
    p.data_referencia,
    (c.data_retirada IS NULL AND c.data_fim_atual < p.data_referencia) AS vencido_em_aberto,
    CASE
        WHEN c.data_retirada IS NULL THEN DATEDIFF(c.data_fim_atual, p.data_referencia)
    END AS dias_para_vencimento
FROM dim_contrato AS c
JOIN dim_obra AS o ON o.id_obra = c.id_obra
JOIN dim_cliente AS cl ON cl.id_cliente = o.id_cliente
CROSS JOIN (
    SELECT CAST(valor AS DATE) AS data_referencia
    FROM ref_parametro
    WHERE chave = 'data_referencia'
) AS p;