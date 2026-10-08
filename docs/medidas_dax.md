# Medidas DAX

As medidas ficam na tabela `_Medidas` do arquivo `powerbi/bi-contratos-obras.pbix`. As pastas de exibição estão entre parênteses.

## Modelo

| De (lado "um") | Para (lado "muitos") |
|---|---|
| `dim_calendario[data]` | `vw_contrato_mes[mes]` |
| `dim_calendario[data]` | `vw_kpi_mensal[mes]` (só para validação) |
| `vw_contrato[id_contrato]` | `vw_contrato_mes[id_contrato]` |
| `vw_contrato[id_contrato]` | `vw_vencimento[id_contrato]` |
| `vw_contrato[id_contrato]` | `vw_recontratacao[id_contrato]` |
| `vw_obra[id_obra]` | `vw_contrato[id_obra]` |

Todas são um-para-muitos com filtro em uma direção. `dim_calendario` está marcada como tabela de datas.

## Conceitos usados

- **Contexto de filtro:** o conjunto de filtros ativo quando a medida é calculada. Em um gráfico por mês, cada coluna tem o filtro de um mês. Segmentações e relações (calendário, contrato, obra) acrescentam filtros.
- **Contexto de linha:** aparece dentro de iteradores como `SUMX`, `AVERAGEX` e `FILTER`, que avaliam uma expressão linha a linha.
- **`CALCULATE`:** avalia uma expressão alterando o contexto de filtro. É a base das medidas de posição atual (por exemplo, a faixa de vencimento) e das janelas móveis.
- **Medida semiaditiva:** carteira e contratos ativos não podem ser somados entre meses. Por isso a medida pega o **último mês** do período.
- **Inteligência temporal:** `TOTALYTD` (acumulado no ano), `DATEADD` (deslocar o período) e `SAMEPERIODLASTYEAR` (mesmo período do ano anterior). Exigem um calendário contínuo, que é a `dim_calendario`.
- **Janela móvel de 12 meses:** filtra a coluna `mes` do fato entre o último mês do contexto e 11 meses antes, depois de remover o filtro do calendário (`REMOVEFILTERS`). Sem remover, o filtro do mês do gráfico continuaria valendo e a janela encolheria para um mês só.
- **`DIVIDE`:** divisão que devolve vazio em vez de erro quando o denominador é zero.
- **Variáveis (`VAR`):** guardam um valor calculado uma vez, o que deixa a fórmula legível e mais rápida.

## Receita (Receita)

```dax
Receita mês anterior =
CALCULATE ( [Receita], DATEADD ( dim_calendario[data], -1, MONTH ) )
```

```dax
Variação da receita vs mês anterior =
VAR atual = [Receita]
VAR anterior = [Receita mês anterior]
RETURN
    DIVIDE ( atual - anterior, anterior )
```

```dax
Receita ano anterior =
CALCULATE ( [Receita], SAMEPERIODLASTYEAR ( dim_calendario[data] ) )
```

```dax
Variação da receita vs ano anterior =
VAR atual = [Receita]
VAR anterior = [Receita ano anterior]
RETURN
    DIVIDE ( atual - anterior, anterior )
```

```dax
Clientes com receita = DISTINCTCOUNT ( vw_contrato_mes[id_cliente] )
```

```dax
Ticket médio = DIVIDE ( [Receita], [Clientes com receita] )
```

`Receita mês anterior` e `Variação ... vs mês anterior` foram feitas para gráficos por mês. Em um ano inteiro, `DATEADD` desloca o intervalo todo em um mês.

## Carteira e movimentação (Carteira)

```dax
Carteira (início do período) =
VAR primeiro_mes = MIN ( vw_contrato_mes[mes] )
RETURN
    CALCULATE (
        SUM ( vw_contrato_mes[carteira_inicio_mes] ),
        vw_contrato_mes[mes] = primeiro_mes
    )
```

```dax
Carteira mês anterior =
CALCULATE ( [Carteira (fim do período)], DATEADD ( dim_calendario[data], -1, MONTH ) )
```

```dax
Variação da carteira vs mês anterior =
VAR atual = [Carteira (fim do período)]
VAR anterior = [Carteira mês anterior]
RETURN
    DIVIDE ( atual - anterior, anterior )
```

```dax
Contratos novos = SUM ( vw_contrato_mes[iniciou_no_mes] )
```

```dax
Contratos retirados = SUM ( vw_contrato_mes[retirado_no_mes] )
```

```dax
Contratos perdidos = SUM ( vw_contrato_mes[perdido_no_mes] )
```

```dax
Valor perdido = SUM ( vw_contrato_mes[valor_perdido_mes] )
```

## Churn (Churn)

```dax
Churn contratual (taxa mensal) =
DIVIDE ( [Contratos perdidos], SUM ( vw_contrato_mes[ativo_no_inicio_mes] ) )
```

```dax
Churn financeiro (taxa mensal) =
DIVIDE ( [Valor perdido], SUM ( vw_contrato_mes[carteira_inicio_mes] ) )
```

```dax
Churn contratual (12 meses) =
VAR ultimo_mes = MAX ( vw_contrato_mes[mes] )
VAR inicio_janela = EDATE ( ultimo_mes, -11 )
VAR primeiro_mes = CALCULATE ( MIN ( vw_contrato_mes[mes] ), REMOVEFILTERS () )
VAR perdas =
    CALCULATE (
        SUM ( vw_contrato_mes[perdido_no_mes] ),
        REMOVEFILTERS ( dim_calendario ),
        vw_contrato_mes[mes] >= inicio_janela,
        vw_contrato_mes[mes] <= ultimo_mes
    )
VAR base =
    CALCULATE (
        SUM ( vw_contrato_mes[ativo_no_inicio_mes] ),
        REMOVEFILTERS ( dim_calendario ),
        vw_contrato_mes[mes] >= inicio_janela,
        vw_contrato_mes[mes] <= ultimo_mes
    )
RETURN
    IF ( NOT ISBLANK ( ultimo_mes ) && inicio_janela >= primeiro_mes, DIVIDE ( perdas, base ) )
```

```dax
Churn financeiro (12 meses) =
VAR ultimo_mes = MAX ( vw_contrato_mes[mes] )
VAR inicio_janela = EDATE ( ultimo_mes, -11 )
VAR primeiro_mes = CALCULATE ( MIN ( vw_contrato_mes[mes] ), REMOVEFILTERS () )
VAR perdas =
    CALCULATE (
        SUM ( vw_contrato_mes[valor_perdido_mes] ),
        REMOVEFILTERS ( dim_calendario ),
        vw_contrato_mes[mes] >= inicio_janela,
        vw_contrato_mes[mes] <= ultimo_mes
    )
VAR base =
    CALCULATE (
        SUM ( vw_contrato_mes[carteira_inicio_mes] ),
        REMOVEFILTERS ( dim_calendario ),
        vw_contrato_mes[mes] >= inicio_janela,
        vw_contrato_mes[mes] <= ultimo_mes
    )
RETURN
    IF ( NOT ISBLANK ( ultimo_mes ) && inicio_janela >= primeiro_mes, DIVIDE ( perdas, base ) )
```

As medidas de 12 meses só existem quando há 12 meses completos de histórico, como na view `vw_kpi_mensal`. A taxa mensal, usada em um período maior que um mês, vira a taxa mensal média ponderada pela base.

## Posição atual: obras e clientes (Posição atual)

Mostram a situação na data de referência e **não respondem ao calendário**.

```dax
Obras ativas =
CALCULATE ( COUNTROWS ( vw_obra ), vw_obra[status_obra] = "ativa" )
```

```dax
Portas em operação =
CALCULATE ( SUM ( vw_obra[qtd_portas] ), vw_obra[status_obra] = "ativa" )
```

```dax
Valor mensal por porta =
DIVIDE ( SUM ( vw_obra[valor_mensal_ativo] ), [Portas em operação] )
```

```dax
Clientes ativos =
CALCULATE ( DISTINCTCOUNT ( vw_contrato[id_cliente] ), vw_contrato[status_contrato] = "ativo" )
```

## Posição atual: vencimento e risco (Vencimento e risco)

```dax
Receita a vencer (0-30 dias) =
CALCULATE ( SUM ( vw_vencimento[valor_mensal] ), vw_vencimento[faixa_vencimento] = "0-30" )
```

```dax
Receita a vencer (31-60 dias) =
CALCULATE ( SUM ( vw_vencimento[valor_mensal] ), vw_vencimento[faixa_vencimento] = "31-60" )
```

```dax
Receita a vencer (61-90 dias) =
CALCULATE ( SUM ( vw_vencimento[valor_mensal] ), vw_vencimento[faixa_vencimento] = "61-90" )
```

```dax
Receita a vencer (90 dias) =
CALCULATE (
    SUM ( vw_vencimento[valor_mensal] ),
    vw_vencimento[faixa_vencimento] IN { "0-30", "31-60", "61-90" }
)
```

```dax
Receita em risco (0-30 dias) =
CALCULATE (
    SUM ( vw_vencimento[valor_mensal] ),
    vw_vencimento[faixa_vencimento] = "0-30",
    vw_vencimento[em_risco] = 1
)
```

```dax
Receita em risco (31-60 dias) =
CALCULATE (
    SUM ( vw_vencimento[valor_mensal] ),
    vw_vencimento[faixa_vencimento] = "31-60",
    vw_vencimento[em_risco] = 1
)
```

```dax
Receita em risco (61-90 dias) =
CALCULATE (
    SUM ( vw_vencimento[valor_mensal] ),
    vw_vencimento[faixa_vencimento] = "61-90",
    vw_vencimento[em_risco] = 1
)
```

```dax
Receita em risco (90 dias) =
CALCULATE ( SUM ( vw_vencimento[valor_mensal] ), vw_vencimento[em_risco] = 1 )
```

```dax
Vencidos em aberto (quantidade) =
CALCULATE ( COUNTROWS ( vw_vencimento ), vw_vencimento[faixa_vencimento] = "vencido_em_aberto" )
```

```dax
Vencidos em aberto (valor) =
CALCULATE ( SUM ( vw_vencimento[valor_mensal] ), vw_vencimento[faixa_vencimento] = "vencido_em_aberto" )
```

```dax
Receita a vencer esperada (90 dias) =
[Receita a vencer (90 dias)] * ( 1 - [Taxa de prorrogação] )
```

## Prazo e recontratação (Prazo)

```dax
Taxa de prorrogação =
VAR referencia = MAX ( vw_contrato[data_referencia] )
VAR resolvidos =
    FILTER (
        vw_contrato,
        vw_contrato[data_fim_prevista_inicial] <= referencia
            || NOT ISBLANK ( vw_contrato[data_retirada] )
            || vw_contrato[prorrogado] = 1
    )
RETURN
    DIVIDE ( SUMX ( resolvidos, vw_contrato[prorrogado] ), COUNTROWS ( resolvidos ) )
```

```dax
Desvio de prazo médio (dias) =
AVERAGEX (
    FILTER ( vw_contrato, vw_contrato[status_contrato] = "encerrado" ),
    vw_contrato[desvio_prazo_dias]
)
```

```dax
Duração real média (dias) =
AVERAGEX (
    FILTER ( vw_contrato, vw_contrato[status_contrato] = "encerrado" ),
    vw_contrato[duracao_real_dias]
)
```

```dax
Duração prevista média (dias) = AVERAGE ( vw_contrato[duracao_prevista_dias] )
```

```dax
Taxa de recontratação (12 meses) =
DIVIDE (
    CALCULATE ( SUM ( vw_recontratacao[recontratou_em_12m] ), vw_recontratacao[janela_completa] = 1 ),
    CALCULATE ( COUNTROWS ( vw_recontratacao ), vw_recontratacao[janela_completa] = 1 )
)
```

## Validação contra o SQL (Validação)

Usam `vw_kpi_mensal`, que o SQL calculou. Servem para a página de validação e devem dar zero.

```dax
Receita (SQL) = SUM ( vw_kpi_mensal[receita] )
```

```dax
Carteira (SQL) = SUM ( vw_kpi_mensal[carteira_fim] )
```

```dax
Churn contratual 12m (SQL) = SUM ( vw_kpi_mensal[churn_contratual_12m] )
```

```dax
Diferença absoluta de receita =
SUMX ( VALUES ( dim_calendario[ano_mes] ), ABS ( [Receita] - [Receita (SQL)] ) )
```

```dax
Diferença absoluta de carteira =
SUMX ( VALUES ( dim_calendario[ano_mes] ), ABS ( [Carteira (fim do período)] - [Carteira (SQL)] ) )
```

```dax
Diferença absoluta de churn 12m =
SUMX (
    VALUES ( dim_calendario[ano_mes] ),
    ABS ( [Churn contratual (12 meses)] - [Churn contratual 12m (SQL)] )
)
```