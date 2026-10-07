# Medidas DAX

As medidas ficam na tabela `_Medidas` do arquivo `powerbi/bi-contratos-obras.pbix`.

## Modelo

| De (lado "um") | Para (lado "muitos") |
|---|---|
| `dim_calendario[data]` | `vw_contrato_mes[mes]` |
| `vw_contrato[id_contrato]` | `vw_contrato_mes[id_contrato]` |
| `vw_obra[id_obra]` | `vw_contrato[id_obra]` |

Todas são um-para-muitos com filtro em uma direção. `dim_calendario` está marcada como tabela de datas.

## Medidas da fatia mínima

| Medida | Fórmula | Observação |
|---|---|---|
| Receita | `SUM ( vw_contrato_mes[receita_mes] )` | Receita proporcional por dias ativos |
| Receita acumulada no ano | `TOTALYTD ( [Receita], dim_calendario[data] )` | Acumulado do ano até o fim do período |
| Carteira (fim do período) | Soma de `carteira_fim_mes` no último mês do período | Medida semiaditiva: não soma meses |
| Contratos ativos (fim do período) | Soma de `ativo_no_fim_mes` no último mês do período | Medida semiaditiva |