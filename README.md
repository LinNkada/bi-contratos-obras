# BI de Contratos e Obras

> **Aviso:** todos os dados deste projeto são **sintéticos**. Nenhum dado real ou confidencial é utilizado.

Projeto de portfólio em Dados/BI: pipeline em Python (ETL e validação), MySQL (staging, dimensões, fatos e views) e Power BI (DAX), simulando a análise financeira e comercial de uma empresa de aluguel de proteções para vão de elevador.

## Status

Em desenvolvimento. Fase atual: 0 (estrutura e configuração).

## Configuração do ambiente

1. Criar e ativar o ambiente virtual: `python -m venv .venv`
2. Instalar dependências: `pip install -r requirements.txt`
3. Copiar `.env.example` para `.env` e preencher as credenciais do MySQL
4. Testar a conexão: `python -m src.db`