# Arquitetura e Plano de Desenvolvimento: B3 Ações Pilot (Antigravity CLI Native + Web UI)

Ferramenta local para macOS em `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot`, orquestrada pelo **`agy cli` (Antigravity)** e equipada com **Interface Web no Navegador** e **Radar de Dividendos/JCP (Data COM)**. Gerencia o ciclo completo de Swing Trade de Ações na B3: estratégias híbridas (60% Reversão / 40% Tendência), alertas matinais via Telegram e macOS, captura programada de proventos e contabilidade fiscal estrita da Receita Federal.

---

## User Review Required

> [!IMPORTANT]
> **Alterações e Decisões Arquiteturais Consolidadas:**
> 1. **Nome e Diretório:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot`.
> 2. **Interface Web no Navegador:**
>    - Implementada em **Streamlit** (ou FastAPI + SSR Clean), mantendo 100% da stack em Python nativo (sem a sobrecarga de gerenciar Node.js / NPM).
>    - **Estética & Acessibilidade:** Modo Claro nativo (*Clean Light*), fontes de sistema, alto contraste (WCAG 2.2 AA) e renderização rápida via gráficos interativos Plotly.
> 3. **Módulo de Dividendos e JCP (Estratégia da Data COM):**
>    - Rastreamento dos anúncios de proventos na B3 com foco no período legal entre o anúncio e a **Data COM** (data de corte para ter direito ao provento).
>    - **Alerta de Risco / Dissenso Construtivo:** Na B3, na *Data EX*, a cotação é descontada no valor exato do provento. Portanto, o sistema só emitirá sinal de compra para dividendos se o papel estiver simultaneamente em **tendência técnica favorável** (evitando comprar ações em queda livre apenas pelo dividendo).
> 4. **Alertas no Telegram:**
>    - 100% das saídas (Stop Loss, Take Profit, Trailing Stop, Time-Stop).
>    - Compras com alta confluência (Score $\ge 8.0$) e anúncios de Data COM com assimetria técnica.

---

## Open Questions

> [!NOTE]
> Questão para validação da interface web:
> 1. **Stack da Interface Web:** A opção por **Streamlit com Plotly** é ideal por ser executada no mesmo ambiente virtual Python com um comando único (`b3pilot web`), sem necessidade de instalar Node.js/Yarn. Você aprova essa stack ou prefere um servidor web desacoplado (FastAPI + React)? *(Recomendamos fortemente Streamlit pela simplicidade e menor consumo de memória no Mac).*

---

## Estrutura do Projeto

```
/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/
├── README.md
├── pyproject.toml              # Dependências (uv / pip)
├── .env.example                # Credenciais do Telegram e configurações
├── b3pilot/
│   ├── __init__.py
│   ├── cli.py                  # Entrypoint dos comandos de terminal
│   ├── config.py               # Configurações de pesos (60/40), risco e temas
│   ├── data/
│   │   ├── __init__.py
│   │   ├── b3_feed.py          # Download e cache de cotações B3 (.SA)
│   │   ├── universe.py         # Universo IBrX-100 / IBOVESPA
│   │   └── dividends_feed.py   # Rastreamento de proventos (Dividendos/JCP, Data COM, Data EX)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── strategies.py       # Algoritmos do IFR2 (60%) e Momentum/Trend (40%)
│   │   ├── dividend_strategy.py# Estratégia de entrada pré-Data COM com filtro de tendência
│   │   ├── screener.py         # Scanner de confluência (Score 0-10)
│   │   └── exits.py            # Motor de saídas (Stop Loss, Take Profit, Trailing Stop ATR)
│   ├── ledger/
│   │   ├── __init__.py
│   │   ├── db.py               # Schemas SQLite (transactions, positions, tax_ledger, dividends_ledger)
│   │   ├── portfolio.py        # Gestão de custódia, preço médio ponderado e PnL
│   │   └── taxes.py            # Motor fiscal (isenção R$ 20k, 15% IR, prejuízos, DARF)
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── notifier.py         # Notificador multicanal (Telegram Bot e macOS osascript)
│   │   └── morning_job.py      # Rotina matinal diária às 09:15 BRT
│   └── web/
│       ├── __init__.py
│       ├── app.py              # Dashboard interativo local (Streamlit + Plotly)
│       └── views/
│           ├── dashboard.py    # Resumo patrimonial, PnL e posições abertas
│           ├── screener_view.py# Radar de compras e calendário de Data COM
│           ├── history_view.py # Histórico de trades e curva de capital
│           └── tax_view.py     # Relatório de IR, isenção R$ 20k e emissão de DARF
└── scripts/
    ├── install_skill.sh        # Registrador da Skill no Antigravity agy
    └── setup_cron.sh           # Instalação do agendador automático no macOS (launchd)
```

---

## Detalhamento dos Novos Módulos

### 1. Módulo de Proventos e Ciclo da Data COM (`b3pilot/data/dividends_feed.py` e `b3pilot/core/dividend_strategy.py`)
* **Monitoramento Ativo:** Captura os anúncios de distribuição de **Dividendos** e **Juros sobre Capital Próprio (JCP)** das ações monitoradas.
* **Mapeamento de Prazos Legais:**
  - **Data do Anúncio (Fato Relevante):** Momento em que a empresa comunica o pagamento ao mercado.
  - **Data COM (Data de Corte):** Prazo final para compra das ações com direito aos proventos.
  - **Data EX:** Primeiro dia de negociação sem o direito aos proventos (cotação ajustada pela B3).
  - **Data de Pagamento:** Crédito efetivo dos valores em conta corrente na corretora.
* **Filtro de "Dividend Momentum":** 
  - Alerta compras com 3 a 7 dias de antecedência da Data COM **apenas** para papéis que apresentem estrutura técnica de alta (Preço > SMA 50) e liquidez diária > R$ 10M, visando capturar tanto o provento quanto a valorização antes da Data EX.
* **Tributação dos Proventos no Ledger:**
  - *Dividendos:* Registrados como rendimento 100% isento e não tributável.
  - *JCP:* Registrados com retenção compulsória de 15% na fonte (imposto já recolhido pela empresa, creditando o valor líquido).

### 2. Interface Web no Navegador (`b3pilot/web/app.py`)
Aberto localmente no navegador via comando `b3pilot web` (rodando em `http://localhost:8501`):
* **Design & Acessibilidade:**
  - Tema Claro (*Clean Light*) por padrão, sem poluição visual ou contraste agressivo.
  - Tipografia baseada em fontes do sistema Apple (SF Pro).
  - Componentes acessíveis com conformidade WCAG 2.2 AA.
* **Abas e Telas:**
  1. **Painel Geral (Overview):**
     - Termômetro de Exposição da Carteira (saldo em caixa vs. alocado em ações).
     - Rentabilidade acumulada (Mark-to-Market) e PnL não realizado.
     - Tabela de posições abertas com preços de Stop Loss, Trailing Stop e Take Profit.
  2. **Radar Matinal & Calendário de Proventos:**
     - Oportunidades do scanner do dia com Score de Confluência e gráfico de suporte/resistência.
     - Próximas **Datas COM** com rendimento estimado (*Dividend Yield* da rodada) e contagem regressiva de pregões.
  3. **Histórico de Trades & Curva de Capital:**
     - Gráfico interativo de evolução do patrimônio (Equity Curve).
     - Métricas de desempenho: Taxa de Acerto (Win Rate), Fator de Lucro (*Profit Factor*) e Payoff médio.
     - Tabela detalhada de compras e vendas encerradas com resultado líquido em R$ e %.
  4. **Gestão Fiscal & DARF:**
     - Barra de progresso do volume de vendas no mês (indicador visual dos R$ 20.000 de isenção).
     - Lucro isento vs. lucro tributável acumulado no ano.
     - Prejuízo residual a compensar em meses futuros.
     - Cálculo exato do DARF (código 6015) com desconto de IRRF ("dedo-duro").

### 3. Integração com Antigravity CLI (`agy`)
* Todos os dados gerados pelo banco SQLite e pelo scanner continuam 100% interoperáveis com a Skill do `agy`.
* O usuário pode consultar tudo tanto pela Interface Web quanto conversando com o `agy` no terminal:
  - `agy "abra a interface web do b3pilot"`
  - `agy "quais ações têm data COM nesta semana?"`
  - `agy "mostre o resumo fiscal do mês"`

---

## Verification Plan

### Testes Automatizados
1. **Regras de Proventos (`pytest tests/test_dividends.py`):**
   * Validar cálculo do direito a proventos com base na data da ordem versus Data COM.
   * Validar segregação contábil entre Dividendo (isento) e JCP (líquido com 15% retido).
2. **Regras Fiscais (`pytest tests/test_taxes.py`):**
   * Validar preço médio ponderado, isenção de R$ 20k e DARF de 15%.
3. **Mecanismo de Saídas e Sinais (`pytest tests/test_core.py`):**
   * Validar Stop Loss, Trailing Stop por ATR e Time Stop.

### Validação Manual
1. **Validação da UI Web:** Iniciar `b3pilot web` e verificar carregamento limpo dos gráficos Plotly, tabelas de posições e painel de impostos.
2. **Validação do Radar de Dividendos:** Rodar `b3pilot dividends` e verificar a listagem de eventos com Data COM próximas.
3. **Validação do Telegram:** Disparo de notificação de teste contendo detalhes de venda e alerta de compra vantajosa.
