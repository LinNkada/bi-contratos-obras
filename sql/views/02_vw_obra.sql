-- vw_obra: um registro por obra, com o status e a carteira ativa.
-- Status: ativa (algum contrato ativo), encerrada (só contratos encerrados)
-- ou sem_contrato.

CREATE OR REPLACE VIEW vw_obra AS
SELECT
    o.id_obra,
    o.id_cliente,
    cl.nome_cliente,
    o.nome_obra,
    o.cidade,
    o.estado,
    o.macro_regiao,
    o.latitude,
    o.longitude,
    o.qtd_portas,
    COUNT(c.id_contrato) AS contratos,
    COUNT(CASE WHEN c.status_contrato = 'ativo' THEN 1 END) AS contratos_ativos,
    COALESCE(SUM(CASE WHEN c.status_contrato = 'ativo' THEN c.valor_mensal END), 0) AS valor_mensal_ativo,
    CASE
        WHEN COUNT(c.id_contrato) = 0 THEN 'sem_contrato'
        WHEN COUNT(CASE WHEN c.status_contrato = 'ativo' THEN 1 END) > 0 THEN 'ativa'
        ELSE 'encerrada'
    END AS status_obra,
    CASE
        WHEN COUNT(CASE WHEN c.status_contrato = 'ativo' THEN 1 END) > 0
        THEN ROUND(SUM(CASE WHEN c.status_contrato = 'ativo' THEN c.valor_mensal END) / o.qtd_portas, 2)
    END AS valor_mensal_por_porta
FROM dim_obra AS o
JOIN dim_cliente AS cl ON cl.id_cliente = o.id_cliente
LEFT JOIN dim_contrato AS c ON c.id_obra = o.id_obra
GROUP BY
    o.id_obra, o.id_cliente, cl.nome_cliente, o.nome_obra, o.cidade, o.estado,
    o.macro_regiao, o.latitude, o.longitude, o.qtd_portas;