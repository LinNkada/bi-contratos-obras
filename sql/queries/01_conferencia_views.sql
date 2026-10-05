USE bi_contratos_obras;

-- Consultas de conferência das views. Rodar depois de python -m src.pipeline.

-- 1. Identidade de controle: ativos no início + iniciados - retirados = ativos no fim.
--    As duas colunas de diferença devem ser 0 (a última, NULL no último mês).
WITH m AS (
    SELECT mes,
           SUM(ativo_no_inicio_mes) AS inicio,
           SUM(iniciou_no_mes)      AS novos,
           SUM(retirado_no_mes)     AS retirados,
           SUM(ativo_no_fim_mes)    AS fim
    FROM vw_contrato_mes
    GROUP BY mes
)
SELECT mes, inicio, novos, retirados, fim,
       inicio + novos - retirados - fim AS diferenca_no_mes,
       fim - LEAD(inicio) OVER (ORDER BY mes) AS diferenca_para_o_proximo
FROM m
ORDER BY mes;

-- 2. Último mês: ativos e carteira no fim do mês devem bater com dim_contrato.
SELECT SUM(ativo_no_fim_mes) AS ativos_view, SUM(carteira_fim_mes) AS carteira_view
FROM vw_contrato_mes
WHERE mes = (SELECT MAX(mes) FROM vw_contrato_mes);

SELECT COUNT(*) AS ativos_dim, SUM(valor_mensal) AS carteira_dim
FROM dim_contrato
WHERE status_contrato = 'ativo';

-- 3. Obras por status, com portas em operação.
SELECT status_obra, COUNT(*) AS obras, SUM(qtd_portas) AS portas, SUM(valor_mensal_ativo) AS carteira
FROM vw_obra
GROUP BY status_obra;

-- 4. Contratos vencidos em aberto.
SELECT id_contrato, nome_cliente, data_fim_atual, dias_para_vencimento, valor_mensal
FROM vw_contrato
WHERE vencido_em_aberto = 1
ORDER BY data_fim_atual;

-- 5. Receita e perdas por ano, para um olhar de sanidade.
SELECT LEFT(ano_mes, 4) AS ano,
       ROUND(SUM(receita_mes), 2) AS receita,
       SUM(perdido_no_mes) AS contratos_perdidos
FROM vw_contrato_mes
GROUP BY LEFT(ano_mes, 4)
ORDER BY ano;

-- 6. Um contrato para conferir à mão (troque o id): datas no CSV, receita mês a mês aqui.
SELECT id_contrato, ano_mes, dias_ativos, receita_mes, iniciou_no_mes, retirado_no_mes, ativo_no_fim_mes
FROM vw_contrato_mes
WHERE id_contrato = 'CTR-0001'
ORDER BY mes;