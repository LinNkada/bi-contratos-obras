# Regras de negócio — v0.2

> Dados sintéticos. Este documento é a fonte de verdade das definições: mudanças aqui precedem mudanças no código.

## Contexto

Empresa que aluga proteções para vão de elevador em obras de prédios. Contratos de escopo fechado, sem renovação. O prazo é uma estimativa de retirada e costuma ser prorrogado.

## Parâmetros

- Data de referência: 2026-09-30 (`REFERENCE_DATE`)
- Histórico: 36 meses (2023-10-01 a 2026-09-30)

## Relações

- Cliente 1—N Obra
- Obra 1—N Contrato (contratos da mesma obra podem ser sequenciais ou simultâneos)

## Datas do contrato

| Campo | Significado |
|---|---|
| `data_inicio` | Início da locação |
| `data_fim_prevista_inicial` | Prazo assinado originalmente |
| `data_fim_atual` | Prazo atual: igual ao inicial se não houve prorrogação |
| `data_retirada` | Retirada real da proteção (vazia se ainda instalada) |

## Regras

- **Dia ativo:** um contrato está ativo no dia D se `data_inicio <= D` e (`data_retirada` vazia ou `D <= data_retirada`). Os dois extremos contam.
- **Contrato ativo na data de referência:** tem dia ativo nessa data.
- **Vencido em aberto:** contrato ativo com `data_fim_atual` anterior à data de referência. Continua ativo e é sinalizado.
- **Obra ativa:** tem ao menos um contrato ativo. Obra encerrada: tem contratos, nenhum ativo.
- **Receita do mês:** `valor_mensal` × dias ativos no mês ÷ dias do mês, arredondada a 2 casas. Premissa: cobrança proporcional por dia.
- **Motivo de encerramento:** `concluido`, `cancelado_cliente` ou `rescindido`.
- **Perda (churn):** apenas `cancelado_cliente` e `rescindido`. `concluido` é saída natural.
- **Prorrogado:** `data_fim_atual` maior que `data_fim_prevista_inicial`.

## Exemplo de conferência

Contrato com `valor_mensal` de 10.000,00, `data_inicio` em 16/03/2026 e `data_retirada` em 10/06/2026:

| Mês | Dias ativos | Receita |
|---|---|---|
| Março | 16 de 31 | 5.161,29 |
| Abril | 30 de 30 | 10.000,00 |
| Maio | 31 de 31 | 10.000,00 |
| Junho | 10 de 30 | 3.333,33 |
| **Total** | | **28.494,62** |

## Indicadores mensais

Calculados pela view `vw_contrato_mes`, um registro por contrato por mês em que a proteção esteve instalada, até a data de referência. No mês da data de referência, o período termina nela.

- **Ativo no início do mês:** `data_inicio` anterior ao primeiro dia do mês, com a proteção ainda instalada nesse dia.
- **Iniciou no mês:** `data_inicio` dentro do período do mês.
- **Retirado no mês:** `data_retirada` dentro do período do mês.
- **Perdido no mês:** retirado no mês com motivo `cancelado_cliente` ou `rescindido`.
- **Ativo no fim do mês:** iniciado até o último dia do período e sem retirada até essa data.
- **Carteira no início e no fim do mês:** soma do `valor_mensal` dos contratos ativos no início e no fim do mês.
- **Identidade de controle:** ativos no início + iniciados − retirados = ativos no fim.

## KPIs (a detalhar nas fases indicadas)

| KPI | Definição resumida | Fase |
|---|---|---|
| Carteira | Soma do `valor_mensal` dos contratos ativos | 5 |
| Receita do mês e acumulada | Soma da receita calculada por mês, e acumulado no ano | 5 |
| Ticket médio | Receita do mês ÷ clientes com receita no mês | 5 |
| Valor mensal médio por contrato | Média do `valor_mensal` dos contratos | 5 |
| Contratos, obras e clientes ativos/encerrados | Contagens pelo status | 5 |
| Duração média | Prevista e real, em dias | 5 |
| Portas em operação | Soma de `qtd_portas` das obras ativas | 5 |
| Valor mensal por porta | Soma do `valor_mensal` dos contratos ativos da obra ÷ `qtd_portas` | 5 |
| Receita a vencer | `valor_mensal` dos ativos por faixa de dias até o `data_fim_atual`: 0-30, 31-60 e 61-90 | 7 |
| Vencidos em aberto | Quantidade e `valor_mensal` dos ativos com `data_fim_atual` anterior à data de referência | 7 |
| Receita a vencer esperada | Receita a vencer de 0 a 90 dias × (1 − taxa de prorrogação) | 7 |
| Receita em risco | Parte da receita a vencer (0 a 90 dias) cujo cliente não tem continuidade | 7 |
| Churn contratual | Perdas no período ÷ contratos ativos no início (12 meses móveis) | 7 |
| Churn financeiro | `valor_mensal` das perdas ÷ carteira no início | 7 |
| Taxa de prorrogação | Prorrogados ÷ contratos com o prazo inicial resolvido | 7 |
| Desvio de prazo | Média de `data_retirada` − `data_fim_prevista_inicial` (encerrados) | 7 |
| Recontratação de clientes | Clientes com novo contrato após o fim de um anterior | 7 |
| Concentração da carteira | Participação dos 5 maiores clientes na carteira | 8 |

## Fora do escopo

Oportunidades, conversão, pipeline e cobertura; receita recebida e inadimplência; histórico de aditivos; segmentação de clientes.