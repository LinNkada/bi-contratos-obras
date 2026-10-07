USE bi_contratos_obras;

-- 1. Receita a vencer e receita em risco por faixa de vencimento.
SELECT faixa_vencimento,
       COUNT(*) AS contratos,
       SUM(valor_mensal) AS receita,
       COUNT(CASE WHEN em_risco = 1 THEN 1 END) AS contratos_em_risco,
       COALESCE(SUM(CASE WHEN em_risco = 1 THEN valor_mensal END), 0) AS receita_em_risco
FROM vw_vencimento
GROUP BY faixa_vencimento
ORDER BY FIELD(faixa_vencimento, 'vencido_em_aberto', '0-30', '31-60', '61-90', 'mais_de_90');

-- 2. Taxa de prorrogação: a definição nova (prazo inicial resolvido) e a antiga (só encerrados).
SELECT
    ROUND(SUM(CASE WHEN data_fim_prevista_inicial <= data_referencia OR data_retirada IS NOT NULL OR prorrogado = 1
                   THEN prorrogado END)
          / COUNT(CASE WHEN data_fim_prevista_inicial <= data_referencia OR data_retirada IS NOT NULL OR prorrogado = 1
                       THEN 1 END), 4) AS taxa_prorrogacao,
    ROUND(SUM(CASE WHEN status_contrato = 'encerrado' THEN prorrogado END)
          / COUNT(CASE WHEN status_contrato = 'encerrado' THEN 1 END), 4) AS taxa_prorrogacao_encerrados
FROM vw_contrato;

-- 3. Desvio de prazo e durações médias.
SELECT
    ROUND(AVG(CASE WHEN status_contrato = 'encerrado' THEN desvio_prazo_dias END), 2) AS desvio_prazo_medio_dias,
    ROUND(AVG(duracao_prevista_dias), 2) AS duracao_prevista_media_dias,
    ROUND(AVG(CASE WHEN status_contrato = 'encerrado' THEN duracao_real_dias END), 2) AS duracao_real_media_dias
FROM vw_contrato;

-- 4. Receita a vencer esperada em 90 dias: receita a vencer x (1 - taxa de prorrogação).
WITH taxa AS (
    SELECT SUM(CASE WHEN data_fim_prevista_inicial <= data_referencia OR data_retirada IS NOT NULL OR prorrogado = 1
                    THEN prorrogado END)
           / COUNT(CASE WHEN data_fim_prevista_inicial <= data_referencia OR data_retirada IS NOT NULL OR prorrogado = 1
                        THEN 1 END) AS taxa_prorrogacao
    FROM vw_contrato
)
SELECT SUM(v.valor_mensal) AS receita_a_vencer_90,
       ROUND(SUM(v.valor_mensal) * (1 - MAX(t.taxa_prorrogacao)), 2) AS receita_a_vencer_esperada_90
FROM vw_vencimento AS v
CROSS JOIN taxa AS t
WHERE v.faixa_vencimento IN ('0-30', '31-60', '61-90');

-- 5. Os contratos em risco, do mais próximo do vencimento ao mais distante.
SELECT id_contrato, nome_cliente, nome_obra, cidade, data_fim_atual, dias_para_vencimento, valor_mensal
FROM vw_vencimento
WHERE em_risco = 1
ORDER BY dias_para_vencimento;