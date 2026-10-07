-- vw_vencimento: um registro por contrato ativo, com a faixa de vencimento
-- e se o cliente tem outro contrato ativo que continua além do prazo deste.
-- Faixas: vencido_em_aberto, 0-30, 31-60, 61-90 e mais_de_90 (dias a partir da data de referência).
-- em_risco: vence em até 90 dias e o cliente não tem continuidade.

CREATE OR REPLACE VIEW vw_vencimento AS
SELECT
    v.*,
    (v.faixa_vencimento IN ('0-30', '31-60', '61-90') AND v.cliente_com_continuidade = 0) AS em_risco
FROM (
    SELECT
        c.id_contrato,
        c.id_obra,
        c.id_cliente,
        c.nome_cliente,
        c.nome_obra,
        c.cidade,
        c.estado,
        c.valor_mensal,
        c.data_fim_atual,
        c.dias_para_vencimento,
        c.vencido_em_aberto,
        CASE
            WHEN c.vencido_em_aberto = 1 THEN 'vencido_em_aberto'
            WHEN c.dias_para_vencimento <= 30 THEN '0-30'
            WHEN c.dias_para_vencimento <= 60 THEN '31-60'
            WHEN c.dias_para_vencimento <= 90 THEN '61-90'
            ELSE 'mais_de_90'
        END AS faixa_vencimento,
        EXISTS (
            SELECT 1
            FROM vw_contrato AS o
            WHERE o.id_cliente = c.id_cliente
              AND o.id_contrato <> c.id_contrato
              AND o.status_contrato = 'ativo'
              AND o.data_fim_atual > GREATEST(c.data_fim_atual, c.data_referencia)
        ) AS cliente_com_continuidade
    FROM vw_contrato AS c
    WHERE c.status_contrato = 'ativo'
) AS v;