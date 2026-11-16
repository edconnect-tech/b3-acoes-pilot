# B3 Ações Pilot 🚀

Assistente quantitativo autônomo e local para **Swing Trade**, **Captura de Proventos (Dividendos e JCP na Data COM)** e **Gestão Fiscal na B3 (Bolsa Brasileira)**.

O sistema opera de forma 100% local e determinística, combinando **modelos matemáticos em Python** (`pandas`, `pandas_ta`, `numpy`), banco de dados relacional **SQLite**, dashboard interativo em **Streamlit** (Modo Claro / Clean), linha de comando nativa (**CLI Typer/Rich**), rotina de alertas matinais (**macOS e Telegram**) e orquestração inteligente via **Antigravity (`agy`)**.

---

## 🏛️ Arquitetura do Sistema

```
b3-acoes-pilot/
├── b3pilot/
│   ├── core/               # Motores quantitativos, estratégias, risco e regimes
│   │   ├── regime.py       # Gatekeeper de Regime de Mercado (Ibovespa)
│   │   ├── strategies.py   # IFR2, Trend Following, 52W Range e Bear Signals
│   │   ├── dividend_strategy.py # Radar Pré-Data COM e captura de proventos
│   │   ├── risk.py         # Position Sizing determinístico (Risco fixo 2%)
│   │   ├── exits.py        # Motor de Saídas (Stop Loss, Alvo, Trailing, Time-Stop)
│   │   └── screener.py     # Scanner unificado com confluência e ranking
│   ├── data/               # Ingestão de dados de mercado e universo B3
│   │   ├── b3_feed.py      # Cache local em Parquet e downloads via yfinance
│   │   ├── sectors.py      # Matriz Setorial B3 e Macro-Clusters de Risco
│   │   └── universe.py     # Universos Top B3 (alta liquidez) e Amplo
│   ├── ledger/             # Livro-razão financeiro, carteira e tributação
│   │   ├── db.py           # Esquema relacional SQLAlchemy (SQLite)
│   │   ├── portfolio.py    # Controle de posições (Reais e Simuladas) e P&L
│   │   └── taxes.py        # Apuração de IRPF, isenção R$ 20k e DARF (Cód. 6015)
│   ├── alerts/             # Rotina de automação matinal (macOS Push + Telegram)
│   │   ├── morning_job.py  # Job diário pré-abertura (09:55 BRT)
│   │   └── telegram.py     # Disparo de mensagens formatadas
│   ├── web/                # Interface visual Streamlit (Modo Claro / Clean)
│   │   └── app.py          # Dashboard, radar, análise gráfica e gestão fiscal
│   └── cli.py              # Interface de Linha de Comando (Typer + Rich)
├── tests/                  # Suíte de testes unitários automatizados (pytest)
└── portfolio.db            # Banco SQLite local persistente
```

---

## 🧠 Regras de Negócio e Lógicas do Core

Toda a lógica de mercado é executada com precisão aritmética de 64 bits em Python, sem dependência de cálculos probabilísticos de LLMs.

### 1. Gatekeeper de Regime de Mercado (`core/regime.py`)
Antes de avaliar compras individuais, o sistema monitora o índice **Ibovespa (`^BVSP`)** para determinar a exposição máxima de capital e autorização de setups:

| Regime | Condição Técnica (Ibovespa) | Ação no Sistema | Multiplicador de Risco |
| :--- | :--- | :--- | :---: |
| **BULL** | $\text{Preço} > \text{SMA}_{200}$ e $\text{EMA}_9 \ge \text{EMA}_{21}$ | Todos os setups liberados (IFR2, Trend, Pivôs, Proventos) | **1.0x** (100% do lote) |
| **CORRECTION** | $\text{Preço} > \text{SMA}_{200}$, mas $\text{EMA}_9 < \text{EMA}_{21}$ | Trend pausado; IFR2 e Pivôs liberados com cautela | **0.75x** (75% do lote) |
| **BEAR** | $\text{Preço} < \text{SMA}_{200}$ | Trend e Proventos pausados; IFR2 ($\text{IFR}_2 \le 5$) e Pivôs autorizados | **0.50x** (50% do lote) |
| **PANIC** | Queda diária $\le -2.5\%$ **OU** retração semanal $\le -5.0\%$ com $\text{IFR}_{14} \le 25$ | **Bloqueio total de compras** (retorna lista vazia) | **0.0x** (Caixa 100%) |

---

### 2. Estratégias Quantitativas (`core/strategies.py`)

#### A. Reversão à Média Institucional — IFR(2) (Larry Connors)
* **Tendência Primária:** Preço obrigatoriamente acima da média móvel aritmética de 200 períodos ($\text{Preço} > \text{SMA}_{200}$).
* **Gatilho de Entrada:** Índice de Força Relativa de 2 períodos ($\text{IFR}_2 \le 10.0$ em Bull Market ou $\text{IFR}_2 \le 5.0$ em Bear Market).
* **Filtro de Liquidez Real:** Volume Financeiro Médio Diário dos últimos 21 dias ($\text{ADTV}_{21} \ge \text{R\$\ 5.000.000}$).
* **Alvo de Lucro:** Superação da máxima dos 2 pregões anteriores ($\text{HIGH}_{2D}$).
* **Saída por Tempo (Time-Stop):** Encerramento compulsório no **5º pregão** se o alvo não tiver sido atingido.
* **Stop Catastrófico Dinâmico:** Ancorado no ATR para calibrar a perda máxima entre $-6\%$ e $-10\%$ conforme a volatilidade do papel: $\text{Stop} = \text{Preço} - \max(\text{Preço} \times 0.06, \min(\text{Preço} \times 0.10, 2.5 \times \text{ATR}_{14}))$.

#### B. Seguidor de Tendência — *Momentum* com *Pullback*
* **Alinhamento Altista:** $\text{Preço} \ge \text{EMA}_9 > \text{EMA}_{21} > \text{SMA}_{200}$ com $\text{EMA}_9$ inclinada para cima.
* **Gatilho de Retração:** Mínima recente testou o suporte da $\text{EMA}_9$ ou $\text{EMA}_{21}$ com candle de reversão comprador ou fechamento cruzando a média para cima.
* **Stop Técnico:** Abaixo da mínima dos últimos 2 candles deduzido de $0.5 \times \text{ATR}_{14}$ (Volatilidade Real).
* **Alvo Assimétrico:** Projeção fixa de **$2.5R$** ($2.5 \times$ o risco assumido).
* **Trailing Stop:** Proteção móvel de lucros baseada em $\text{Preço} - 2.0 \times \text{ATR}_{14}$.

#### C. Retomada de Fundo — Pivô Concluído / Teste de Suporte
* **Desconto Estrutural:** Posição no Range 52S $\le 75\%$ com folga até a máxima anual $\ge 12\%$ e $\text{IFR}_{14} \le 63.0$.
* **Gatilho de Entrada:** Preço cruzou e fechou acima da $\text{EMA}_9$ com candle de reversão verde e suporte estável após período de sangria.
* **Stop Técnico no Fundo:** $\min(\text{Low}_t, \text{Low}_{t-1}, \text{Low}_{t-2}) - 0.4 \times \text{ATR}_{14}$.
* **Alvo Assimétrico:** Projeção fixa de **$2.5R$**.

---

### 3. Scanner Concorrente de Alta Velocidade (`core/screener.py`)
* Processamento paralelo via `ThreadPoolExecutor` com 12 workers concorrentes.
* Varredura do universo completo (86+ ativos) reduzida de **~80 segundos para ~4.8 segundos**.
* Compatível com a barra de progresso interativa do `rich` no terminal e na interface Web.

---

### 3. Lógica do Range Anual de 52 Semanas (252 Pregões)

Para evitar comprar ativos esticados no topo do canal anual e selecionar papéis com **ampla pista livre até a resistência**, o sistema calcula:

1. **Posição no Canal Anual:**
   $$\text{Range}_{52S} (\%) = \frac{\text{Preço} - \text{Mínima}_{52S}}{\text{Máxima}_{52S} - \text{Mínima}_{52S}} \times 100$$
2. **Distância até a Máxima de 52 Semanas:**
   $$\text{Distância Topo}_{52S} (\%) = \frac{\text{Máxima}_{52S} - \text{Preço}}{\text{Preço}} \times 100$$
3. **Relação Espaço até Resistência vs Risco:**
   $$\text{Assimetria Resistência} = \frac{\text{Máxima}_{52S} - \text{Preço}}{\text{Preço} - \text{Stop Loss}}$$

#### Pontuação Dinâmica:
* **Bonificação de Assimetria (+1.0 ponto):** Ativos com folga $\ge 8\%$ até a máxima anual e relação Espaço/Risco $\ge 2.0\times$ recebem nota extra por assimetria desobstruída.
* **Bonificação Moderada (+0.5 ponto):** Ativos com folga entre $4\%$ e $8\%$ até a máxima anual.
* **Filtro de Exaustão de Topo (-1.0 ponto e Alerta Visual):** Ativos colados a menos de $2\%$ da máxima de 52 semanas com $\text{IFR}_{14} > 68$ recebem desconto na nota e aviso de risco iminente de falso rompimento ou realização de lucros.

---

### 4. Captura de Proventos — Pré-Data COM (`core/dividend_strategy.py`)
* Rastreia anúncios de proventos (**Dividendos e JCP**) com **Data COM** nos próximos 15 dias.
* Filtra papéis que estejam acumulando em tendência de alta para evitar armadilhas de desvalorização ex-dividendo.
* Calcula o desconto projetado na Data EX e o rendimento percentual esperado.

---

### 5. Gestão de Risco e Dimensionamento de Lote (`core/risk.py`)
* **Critério de Risco Fixo:** Risco máximo de **2% do patrimônio líquido** por trade.
* **Cálculo do Lote Sugerido:**
  $$\text{Ações} = \left\lfloor \frac{\text{Capital} \times \text{RiscoPct} \times \text{MultiplicadorRegime}}{\text{Preço de Entrada} - \text{Stop Loss}} \right\rfloor$$
* **Arredondamento Inteligente:** Ajusta para lotes padrão de 100 ações (mercado integral) ou fracionário.
* **Teto de Alocação por Ativo:** Nenhuma posição pode comprometer mais de **25% do capital total**, evitando risco de ruína ou concentração excessiva.

---

### 6. Matriz Setorial, Macro-Clusters e Gestão de Correlação Cruzada (`data/sectors.py` & `core/risk.py`)

Para eliminar o risco da **falsa diversificação** — quando o investidor compra empresas aparentemente distintas que, na realidade, respondem ao mesmo choque macroeconômico e despencam juntas —, o sistema implementa uma camada de inteligência setorial e macro-clusters de risco:

#### O Caso Crítico: Banco do Brasil (`BBAS3`) + Agronegócio
* **A Armadilha:** O investidor adquire ações do Banco do Brasil acreditando estar posicionado no setor bancário defensivo e, simultaneamente, compra ações de empresas agrícolas (como `SOJA3`, `SMTO3`, `AGRO3`, `SLCE3`).
* **A Realidade Institucional:** O Banco do Brasil é o maior financiador do agronegócio do país, detendo mais de **50% de participação no crédito rural** e mais de **35% de sua carteira de crédito total** vinculada ao campo.
* **O Risco Sistêmico:** Em safras com quebra de produção, retração no preço de commodities (soja, milho, açúcar) ou pedidos em série de recuperação judicial de produtores rurais, a inadimplência agrícola e as provisões para devedores duvidosos do BB aumentam expressivamente. **O resultado é uma queda simultânea de BBAS3 e das ações do agronegócio.**
* **A Blindagem do B3 Pilot:** O ativo `BBAS3` possui dupla classificação no sistema: `FINANCEIRO_BANCOS` e `AGRONEGOCIO`. Qualquer tentativa de sobrepor posições de crédito rural e agronegócio é imediatamente bloqueada ou sinalizada com alerta de alto risco.

#### Mapeamento dos Macro-Clusters de Risco da B3
Cada ativo é catalogado com suas vulnerabilidades sistêmicas comuns:

| Macro-Cluster | Ativos Típicos Mapeados | Fatores de Risco Sistêmico / Gatilho de Queda Conjunta |
| :--- | :--- | :--- |
| **`AGRONEGOCIO`** | `SOJA3`, `SMTO3`, `AGRO3`, `SLCE3`, `TTEN3`, `KEPL3`, `JALL3`, `CAML3`, `BBAS3`* | Clima/seca, quebra de safra, preços internacionais de grãos e inadimplência rural. |
| **`PETROLEO_E_GAS`** | `PETR3`, `PETR4`, `PRIO3`, `RECV3`, `VBBR3`, `UGPA3`, `CSAN3` | Cotação global do barril de petróleo tipo Brent e margens de refino. |
| **`MINERACAO_E_SIDERURGIA`** | `VALE3`, `BRAP4`, `CSNA3`, `GGBR4`, `USIM5` | Preço do minério de ferro em Qingdao/Dalian e demanda de construção na China. |
| **`CONSTRUCAO_CIVIL`** | `CYRE3`, `DIRR3`, `CURY3`, `TEND3`, `LAVV3`, `PLPL3` | Curva longa de juros (DI futuro), taxas de financiamento imobiliário e custo INCC. |
| **`VAREJO_E_CONSUMO`** | `LREN3`, `MGLU3`, `CEAB3`, `ALOS3`, `MULT3`, `VULC3` | Endividamento das famílias, taxa Selic elevada e contração do poder de compra. |
| **`FINANCEIRO_BANCOS`** | `ITUB4`, `BBDC4`, `SANB11`, `BPAC11`, `B3SA3`, `BBAS3` | Spread bancário, inadimplência corporativa e volatilidade do mercado de capitais. |
| **`UTILIDADE_PUBLICA`** | `TAEE11`, `CPLE3`, `CMIG4`, `EGIE3`, `ALUP11`, `EQTL3`, `SBSP3` | Risco hidrológico, taxa de desconto real (NTN-B) e reajustes regulatórios (Aneel/Arsesp). |
| **`PAPEL_E_CELULOSE`** | `SUZB3`, `KLBN11` | Cotação internacional da celulose BHKP e taxa de câmbio USD/BRL. |
| **`FRIGORIFICOS_PROTEINA`**| `JBSS3`, `BRFS3`, `BEEF3`, `MRFG3` | Ciclo do gado, preço dos grãos para ração (soja/milho) e barreiras sanitárias. |
| **`SAUDE_E_FARMACIA`** | `RADL3`, `HAPV3`, `FLRY3`, `HYPE3`, `BLAU3`, `PNVL3` | Sinistralidade médica (MLR), reajustes da ANS e poder de compra de medicamentos. |
| **`TECNOLOGIA_E_TELECOM`** | `TOTS3`, `POSI3`, `INTB3`, `TIMS3`, `VIVT3`, `FIQE3` | Ciclos de Capex corporativo, competição tarifária e taxas de juros de longo prazo. |
| **`BENS_DE_CAPITAL`** | `WEGE3`, `EMBJ3`, `POMO4`, `RAPT4`, `FRAS3`, `MYPK3`, `SHUL4` | Atividade industrial, exportações, custos de aço e renovação de frotas pesadas. |
| **`LOGISTICA_E_TRANSPORTE`**| `CCRO3`, `RAIL3`, `RENT3`, `SIMH3`, `TGMA3`, `PORT3`, `STBP3` | Volume de comércio exterior, tráfego rodoviário e escoamento de safras. |

*\*Nota: BBAS3 possui correlação cruzada documentada com o cluster rural em razão de sua carteira de crédito.*

#### Regras de Governança e Seleção Anti-Cluster
1. **Teto Setorial Prudencial:** Nenhuma carteira pode manter mais de **35% do capital alocado em um único setor**.
2. **Limite de Trades Ativos por Macro-Cluster:** Máximo de **1 operação simultânea por cluster** (evitando ter simultaneamente SOJA3 + SMTO3 + BBAS3).
3. **Score de Diversificação da Carteira (0 a 100):** Avalia a saúde da carteira, penalizando agrupamentos correlacionados e concentrações desproporcionais:
   * $\ge 80$: **Excelente** (Descorrelacionada e protegida contra choques).
   * $60 - 79$: **Moderada** (Atenção a sobreposições pontuais).
   * $< 60$: **Crítica** (Alta probabilidade de perdas em cadeia).
4. **Filtro de Descorrelação no Screener e Morning Job (`filter_diversified_signals`):**
   * Ao ranquear as melhores compras, o algoritmo descarta ativos que colidam com clusters já detidos na custódia do investidor.
   * Garante que as 3 recomendações matinais pertençam a **setores 100% independentes** entre si.
5. **Auditoria Reativa Pré-Ordem:** O terminal (`b3pilot buy`), a boleta do Dashboard Web e o Chat emitem avisos explicativos antes de qualquer compra caso o papel aumente o risco de correlação.

---

### 7. Motor de Saídas Contínuo (`core/exits.py`)
Monitora diariamente todas as posições abertas (reais e simuladas), avaliando:
1. **Stop Loss Atingido:** Cotação $\le \text{Stop Loss}$ $\rightarrow$ Venda imediata com **Urgência ALTA**.
2. **Alvo de Realização Parcial (TP1):** Cotação $\ge \text{Alvo Parcial}$ $\rightarrow$ Venda de 50% da posição e subida do stop para garantir lucro no pior caso (**Urgência MÉDIA**).
3. **Alvo Final (Take Profit):** Cotação $\ge \text{Alvo}$ $\rightarrow$ Venda de encerramento total (**Urgência MÉDIA**).
4. **Trailing Stop Acionado:** Ativação da média móvel/ATR trailing para proteger ganhos em papéis de tendência.
5. **Time-Stop no IFR2:** Saída na abertura do 5º pregão caso não tenha batido alvo nem stop.

---

### 8. Realização Parcial (Scale-Out) & Roteiro Home Broker (`ledger/portfolio.py`)
* **Eliminação de Risco:** Venda de 50% das ações ao bater o TP1 e elevação do stop das ações remanescentes para breakeven ou lucro travado.
* **Cálculo de Lucro Garantido (Pior Caso):**
  $$\text{PnL Mínimo} = \text{Lucro da Parcial} + [(\text{Novo Stop} - \text{Preço Médio}) \times \text{Qtd Restante}]$$
* **Roteiro Passo a Passo no Home Broker:**
  1. Cancelar o Stop anterior da quantidade total;
  2. Vender a mercado a metade da posição;
  3. Cadastrar o Novo Stop para as ações restantes.
* **Preservação de Preço Médio:** Mantém a exatidão do custo médio das ações restantes para conformidade com a Receita Federal.

---

## 🖥️ Funcionalidades do Aplicativo

### 1. Interface Web Interativa (Streamlit)
Execute localmente com `b3pilot web` ou `streamlit run b3pilot/web/app.py`:
* **Estética Clean / Modo Claro:** Tipografia de sistema legível, contrastes com certificação WCAG e sem dark mode forçado.
* **💬 Assistente & Chat Operacional:**
  * Área interativa para questionar antes de abrir ou encerrar ordens (ex: *"Posso comprar PETR4 agora?"*, *"Devo vender VALE3 hoje?"*).
  * Veredito técnico instantâneo: **COMPRA**, **VENDA** ou **AGUARDAR**, cruzando IBOVESPA, Médias, IFR2, Range de 52S, **Setores/Clusters** e custódia em aberto.
  * **Alerta Setorial Ativo:** Se o ativo consultado colidir com clusters já detidos em custódia (ex: já possui BBAS3 e pergunta sobre SOJA3 ou SMTO3), o chat emite aviso preventivo de concentração de risco.
  * **Simulador de Parciais em Linguagem Natural:** Ex: *"Simular parcial de SOJA3 vendendo a 8,60 e novo stop a 8,25"* $\rightarrow$ Cálculo exato do lucro no bolso e lucro mínimo garantido no pior caso.
  * Botões de atalho rápido (*chips*) para checagem imediata de saídas, regime e melhores compras descorrelacionadas.
* **Dashboard Executivo & Radiografia Setorial:**
  * Métricas consolidadas de patrimônio líquido, lucro acumulado, gráfico de evolução e assistente de **Scale-Out**.
  * **Painel de Diversificação Setorial:** Gráfico Donut de setores B3, barras de exposição a Macro-Clusters, métrica do **Score de Diversificação (0 a 100)** e alertas explícitos de risco concentrado.
* **Radar de Oportunidades (Screener):**
  * Tabela com Notas de Confluência (0 a 10), Setor, Segmento, Fator de Risco Macro, Diversificação com a Carteira, preços de entrada, stop, alvo e posição no **Range 52S**.
  * **Filtros Avançados:** Filtro por Setor da B3 e toggle de segurança para **Ocultar ativos correlacionados à minha custódia atual**.
  * **Navegação Integrada:** Clique em qualquer linha para abrir a análise gráfica detalhada do papel.
* **Boleta de Nova Compra com Auditoria em Tempo Real:**
  * Ao digitar o ticker, o sistema analisa imediatamente as posições já em carteira e avisa se a compra violará a política de isolamento de risco (ex: alertando sobre a correlação de crédito rural e agronegócio).
* **Análise Gráfica & Variações (1D a 10 Anos):**
  * Candlestick com EMA 9, EMA 21, SMA 50, SMA 200, IFR2, IFR14 e ATR.
  * Tabela de rentabilidade histórica: 1 Dia, 5 Dias, 1 Mês, 6 Meses, 1 Ano, 2 Anos, 5 Anos e 10 Anos.
* **Módulo de Tributação e DARF:** Extrato mensal, compensação de perdas e cálculo de imposto a pagar.
* **Gestão de Carteira:** Visualização separada e comparativa entre **Carteira Real** e **Carteira Simulada** (*paper trading*).

---

### 2. Gestão Fiscal e Apuração de DARF (`ledger/taxes.py`)
Desenvolvido em estrita conformidade com as regras da Receita Federal do Brasil para operações de *Swing Trade* com ações:
* **Preço Médio Ponderado:** Recálculo a cada nova compra considerando taxas de corretagem e emolumentos da B3.
* **Isenção de R$ 20.000/Mês:** Isenta do imposto sobre ganho de capital as vendas cujo valor total alienado no mês calendário não ultrapasse R$ 20.000,00 (Art. 59 da IN RFB nº 1.585/2015).
* **Compensação Automática de Prejuízos:** Abate perdas líquidas acumuladas de meses anteriores antes de tributar novos ganhos.
* **Emissão de DARF:** Aplica a alíquota legal de **15%** sobre o ganho líquido tributável e fornece os dados prontos para pagamento no **Código de Receita 6015**.

---

### 3. Interface de Linha de Comando (CLI `b3pilot`)
Comandos práticos e rápidos via terminal:

```bash
# Executa a varredura quantitativa do mercado com confluência e 52W Range
b3pilot scan

# Varredura somente de oportunidades de altíssima convicção (Score >= 8.0 e R/R >= 2.2)
b3pilot scan --high-conviction

# Exibe extrato de posições abertas na carteira com P&L em tempo real
b3pilot portfolio

# Avalia disparos de Stop Loss, Alvos, Trailing Stops, Time-Stops e Parciais
b3pilot exits

# Executa Realização Parcial com elevação de Stop e roteiro para Home Broker
b3pilot partial-sale SOJA3 31 8.60 --new-stop 8.25

# Inicia monitor contínuo intradiário com alertas de toque no Telegram e Mac
b3pilot watch --interval 300

# Apuração de imposto de renda e emissão de DARF mensal (ano/mês)
b3pilot taxes --month 2026-10

# Calendário de próximas Datas COM para captura de dividendos
b3pilot dividends

# Registra compra com Stop, TP1 (Parcial) e TP2 (Alvo Final)
b3pilot buy PETR4 200 38.50 --strategy TREND --stop 36.20 --tp1 41.50 --target 44.00

# Registra venda e liquida posição
b3pilot sell PETR4 200 42.10

# Consulta o Assistente Operacional direto no terminal
b3pilot ask "Posso comprar PETR4 agora?"
b3pilot ask "Simular parcial de SOJA3 a 8.60 com novo stop a 8.25"

# Inicia o painel visual no navegador
b3pilot web
```

---

### 4. Alertas Matinais Automatizados (`alerts/morning_job.py`)
Rotina programada para ser executada antes da abertura do pregão (09:55 BRT):
* **Auditoria Prévia de Concentração da Carteira:** Detecta se há sobreposição setorial na custódia e emite alerta com Score de Diversificação antes da abertura.
* **Notificações Push nativas no macOS:** Alerta sonoro e visual sobre ordens críticas de saída.
* **Disparo via Bot do Telegram:**
  * Diagnóstico do Regime do Ibovespa;
  * **100% dos alertas de venda** (Stops, Alvos atingidos e Time-Stops);
  * **Top 3 Compras Vantajosas 100% Descorrelacionadas:** Filtradas pelo algoritmo anti-cluster para garantir que nenhum papel compartilhe fatores de risco com posições em aberto na carteira do investidor nem repita setores entre as recomendações.

---

### 5. Integração com o Antigravity (`agy`)
Integrado via Skill nativa no Antigravity (`.gemini/config/skills/b3-acoes-pilot/SKILL.md`). Permite solicitar em linguagem natural:
> *"Qual a situação atual da minha carteira?"*  
> *"Rode o scanner de compras com foco em papéis com espaço até o topo anual."*  
> *"Verifique se tenho concentração de risco ou ações que caem juntas na carteira."*  
> *"Preciso pagar DARF esse mês? Como estão os prejuízos a compensar?"*

---

## 🚀 Instalação e Configuração

### Requisitos
* Python 3.11 ou superior
* macOS, Linux ou WSL

### Passo a Passo

```bash
# 1. Clone o repositório
git clone https://github.com/ricardoneves/b3-acoes-pilot.git
cd b3-acoes-pilot

# 2. Crie e ative o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale o pacote em modo editável com as dependências
pip install -e .

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com seu TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (opcional)

# 5. Execute os testes unitários
pytest
```

---

## 🧪 Testes Automatizados

O sistema conta com suíte de testes unitários com **35 testes automatizados** garantindo a robustez dos cálculos matemáticos, das regras tributárias e da blindagem contra correlação de setores:

```bash
pytest -v
```

Cobertura dos testes:
* `tests/test_sector_correlation.py`: Mapeamento setorial B3, correlação cruzada de risco rural entre BBAS3 e empresas agrícolas, cálculo do Score de Diversificação e filtro de seleção anti-cluster.
* `tests/test_chat.py`: Motor conversacional, extração de tickers B3, decisões pré-trade, alertas de sobreposição setorial e simulação de realização parcial.
* `tests/test_scale_out.py`: Realização parcial (50%), cálculo de lucro garantido no pior caso, preservação do Preço Médio e detecção em saídas.
* `tests/test_core.py`: Indicadores técnicos, métricas de 52 semanas, setups IFR2, Trend Following, Retomada de Fundo (Pivôs) e disparos de saída.
* `tests/test_risk_regime.py`: Transições de regimes de mercado (Bull, Correction, Bear e Pânico cumulativo semanal) e dimensionamento de risco por trade.
* `tests/test_simulation.py`: Coexistência de posições reais e simuladas no banco de dados.
* `tests/test_taxes.py`: Preço médio ponderado com corretagem, isenção de R$ 20k, compensação de prejuízos e DARF 15%.

---

## ⚖️ Licença e Isenção de Responsabilidade

Este software tem finalidade estritamente analítica e educacional. O uso dos setups quantitativos e das sugestões de lote não constitui recomendação pública de investimento. O usuário é o único responsável pela tomada e execução de suas decisões financeiras na B3.
