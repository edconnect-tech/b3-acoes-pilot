# Especificações Técnicas e Arquiteturais — B3 Ações Pilot 🚀

**Versão:** 0.4.0  
**Stack Principal:** Python 3.11+, Streamlit, Plotly, SQLAlchemy (SQLite), Typer, Rich, pandas, pandas-ta, yfinance.  
**Arquitetura:** Local-First, Zero Trust no LLM (cálculos 100% determinísticos em Python de 64 bits), Concorrência Multithread no Scanner, Isolamento de Ambientes (Real vs. Simulado), Blindagem Anti-Cluster de Correlação Cruzada e Modo Claro Acessível (WCAG 2.2 AA).

---

## 1. Visão Geral e Propósito

O **B3 Ações Pilot** é um sistema analítico, operacional e fiscal projetado para investidores pessoa física que operam **Swing Trade** e **Captura de Proventos** na Bolsa Brasileira (B3).

### Premissas Fundamentais
1. **Determinismo Numérico Absoluto:** Todo cálculo de indicador técnico (IFR, Médias, ATR, 52W Range), dimensionamento de risco (2% por trade) e apuração de IRPF é executado por código Python estrito e testado via `pytest`. Nenhuma aritmética financeira é delegada a modelos de linguagem probabilísticos.
2. **Gatekeeper Sistêmico:** Nenhuma operação de compra é autorizada sem validação prévia da tendência macro do Ibovespa (`^BVSP`).
3. **Conformidade Tributária Estrita:** Controle automático de Preço Médio Ponderado com taxas, aferição da isenção legal de R$ 20.000/mês (Art. 59 da IN RFB nº 1.585/2015), compensação de prejuízos acumulados e cálculo do DARF no Código 6015 (alíquota de 15%).
4. **Coexistência de Ambientes:** Separação estrita no banco relacional entre **Custódia Real** e **Laboratório de Simulação (Paper Trading)**.

---

## 2. Arquitetura de Módulos

```
b3pilot/
├── core/                   # Regras de Negócio e Algoritmos Quantitativos
│   ├── regime.py           # Classificador de Regime de Mercado do Ibovespa
│   ├── strategies.py       # Indicadores, Setups (IFR2, Trend, 52W Range, Bear Signals)
│   ├── dividend_strategy.py# Radar Pré-Data COM e cálculo de proventos
│   ├── risk.py             # Position Sizing determinístico e auditoria de travas
│   ├── exits.py            # Motor de Saídas (Stop Loss, Alvo, Trailing, Time-Stop)
│   ├── screener.py         # Scanner de confluência multi-estratégia
│   └── chat.py             # Motor analítico conversacional para tomada de decisão
├── ledger/                 # Livro-Razão Financeiro e Tributação
│   ├── db.py               # Esquema relacional SQLite (SQLAlchemy ORM)
│   ├── portfolio.py        # Execução de ordens (Buy/Sell), P&L e idempotência
│   └── taxes.py            # Apuração mensal de IRPF e geração de DARF
├── data/                   # Ingestão e Processamento de Dados de Mercado
│   ├── b3_feed.py          # Cache local em Parquet e integração yfinance
│   ├── dividends_feed.py   # Rastreamento de proventos e datas de corte
│   ├── sectors.py          # Matriz Setorial B3 e Macro-Clusters de Risco
│   └── universe.py         # Universos de ativos (Top B3 alta liquidez e Amplo)
├── alerts/                 # Automação de Alertas Pré-Abertura
│   ├── morning_job.py      # Job agendado às 09:55 BRT
│   └── notifier.py         # Notificações Push macOS e Telegram Bot API
├── web/                    # Dashboard Visual Interativo
│   └── app.py              # Aplicação Streamlit com gráficos Plotly (Modo Claro)
└── cli.py                  # Interface de Linha de Comando Typer + Rich
```

---

## 3. Especificações do Core Quantitativo

### 3.1. Gatekeeper de Regime de Mercado (`core/regime.py`)
Monitora o índice Ibovespa (`^BVSP`) e classifica o mercado em 4 estados determinísticos:

| Regime | Regra Técnica | Ação Operacional | Multiplicador de Risco ($M_{regime}$) |
| :--- | :--- | :--- | :---: |
| **BULL** | $\text{Preço} > \text{SMA}_{200}$ e $\text{EMA}_9 \ge \text{EMA}_{21}$ | Todos os setups liberados (IFR2, Trend, Pivôs, Dividendos) | **1.0x** |
| **CORRECTION** | $\text{Preço} > \text{SMA}_{200}$, mas $\text{EMA}_9 < \text{EMA}_{21}$ | Trend pausado; IFR2 e Pivôs liberados com cautela | **0.75x** |
| **BEAR** | $\text{Preço} < \text{SMA}_{200}$ | Trend e Dividendos bloqueados; IFR2 (sobrevenda $\le 5$) e Pivôs liberados | **0.50x** |
| **PANIC** | Queda intradiária $\le -2.5\%$ **OU** retração semanal $\le -5.0\%$ com $\text{IFR}_{14} \le 25$ | **Bloqueio total de compras** (retorna lista vazia) | **0.0x** |

---

### 3.2. Estratégias de Swing Trade (`core/strategies.py`)

#### A. Reversão à Média Institucional — IFR(2) (Larry Connors)
* **Tendência Primária:** $\text{Preço Fechamento} > \text{SMA}_{200}$.
* **Gatilho de Entrada:** $\text{IFR}_2 \le 10.0$ (ou $\text{IFR}_2 \le 5.0$ em regime BEAR).
* **Filtro de Liquidez Real:** Volume Financeiro Médio Diário $\text{ADTV}_{21} \ge \text{R\$\ 5.000.000}$.
* **Alvo Imediato:** $\text{HIGH}_{2D}$ (Máxima dos últimos 2 pregões).
* **Saída por Tempo (Time-Stop):** Encerramento compulsório no **5º pregão** se não atingir alvo nem stop.
* **Stop Catastrófico Dinâmico:** Ancorado no ATR para evitar perdas excessivas em papéis lentos ou violinos em alta volatilidade:
  $$\text{Stop Loss} = \text{Preço} - \max(\text{Preço} \times 0.06, \min(\text{Preço} \times 0.10, 2.5 \times \text{ATR}_{14}))$$
* **Pontuação (Score de Confluência):** Base 7.0 + bônus de pânico extremo ($\text{IFR}_2 \le 5.0 \to +1.5$), volume de exaustão ($> 1.2\text{x ADTV} \to +1.0$) e liquidez institucional ($\ge \text{R\$\ 20M} \to +0.5$).

#### B. Seguidor de Tendência — *Momentum* com *Pullback*
* **Alinhamento Altista:** $\text{Preço} \ge \text{EMA}_9 > \text{EMA}_{21} > \text{SMA}_{200}$ com $\text{EMA}_9$ ascendente.
* **Gatilho de Retração:** Mínima recente testou suporte na região da $\text{EMA}_9$ ou $\text{EMA}_{21}$ acompanhada de candle de reversão verde ou fechamento rompendo a média para cima.
* **Stop Técnico:** $\min(\text{Low}_t, \text{Low}_{t-1}) - 0.5 \times \text{ATR}_{14}$.
* **Alvo Assimétrico:** $\text{Preço} + 2.5 \times \text{Risco}$ (Projeção fixa de $2.5R$).
* **Trailing Stop:** $\text{Preço} - 2.0 \times \text{ATR}_{14}$.

#### C. Retomada de Fundo — Pivô Concluído / Teste de Suporte
* **Desconto Estrutural:** Posição no Range 52S $\le 75\%$ com folga até a máxima de 52 semanas $\ge 12\%$ e $\text{IFR}_{14} \le 63.0$.
* **Gatilho Técnico de Pivô:** Preço cruzou e fechou acima da $\text{EMA}_9$ com candle de força compradora ($\text{Close} \ge \text{Open}$ e $\text{Close} > \text{Close}_{t-1}$), acompanhado de base de suporte duplo estável.
* **Stop Técnico no Fundo:** $\min(\text{Low}_t, \text{Low}_{t-1}, \text{Low}_{t-2}) - 0.4 \times \text{ATR}_{14}$.
* **Alvo Assimétrico:** Projeção fixa de $2.5R$ ou retorno à média lenta.
* **Pontuação:** Base 7.5 + bônus de volume de retomada ($+1.0$), upside livre $\ge 25\%$ ($+1.0$) e confluência com $\text{SMA}_{200}$ ($+0.5$).

---

### 3.3. Módulo de Range Anual de 52 Semanas (252 Pregões)

Implementado para balancear o *Momentum* com a **Assimetria até a Resistência**, evitando compras de topo esticado:

1. **Posição no Canal Anual:**
   $$\text{Range}_{52S} (\%) = \frac{\text{Preço} - \text{Mínima}_{52S}}{\text{Máxima}_{52S} - \text{Mínima}_{52S}} \times 100$$
2. **Distância até a Máxima Anual:**
   $$\text{Distância Topo}_{52S} (\%) = \frac{\text{Máxima}_{52S} - \text{Preço}}{\text{Preço}} \times 100$$
3. **Relação Espaço até Resistência vs Risco:**
   $$\text{Assimetria Resistência} = \frac{\text{Máxima}_{52S} - \text{Preço}}{\text{Preço} - \text{Stop Loss}}$$

#### Regras de Pontuação e Filtros:
* **Bonificação de Assimetria (+1.0 ponto):** Ativos com folga $\ge 8\%$ até a máxima anual e relação Espaço/Risco $\ge 2.0\times$ recebem nota máxima por pista livre até a resistência.
* **Bonificação Moderada (+0.5 ponto):** Ativos com folga entre $4\%$ e $8\%$ até o topo anual.
* **Filtro de Exaustão de Topo (-1.0 ponto e Alerta Visual):** Ativos a menos de $2\%$ da máxima anual com $\text{IFR}_{14} > 68$ sofrem penalidade na nota e emitem alerta de sobrecompra com alto risco de falso rompimento.

---

### 3.4. Motor de Chat & Decisão Pré-Trade (`core/chat.py`)
Mecanismo determinístico para responder dúvidas do investidor antes de emitir uma ordem:
* **Extração de Tickers:** Parser via Regex para ativos B3 (`[A-Za-z]{4}(?:3|4|5|6|11)`).
* **Decisões para Posições Abertas:**
  * $\text{Preço} \le \text{Stop Loss} \to$ **🔴 VENDA OBRIGATÓRIA (STOP LOSS ATINGIDO)**
  * $\text{Preço} \ge \text{Alvo} \to$ **🟢 REALIZAR LUCROS (ALVO ATINGIDO)**
  * Estrutura baixista armada $\to$ **⚠️ ATENÇÃO: PRESSÃO VENDEDORA DETECTADA**
  * Oscilação normal $\to$ **🟡 MANTER POSIÇÃO (EM ANDAMENTO)**
* **Hierarquia Decisória para Novas Compras:**
  1. Pânico no IBOVESPA $\to$ **🚨 COMPRA PROIBIDA (PÂNICO SISTÊMICO)**
  2. Setup IFR2 ativo $\to$ **🟢 COMPRA RECOMENDADA (IFR2 Ativo)**
  3. Setup Retomada de Fundo $\to$ **🟢 COMPRA RECOMENDADA (Retomada de Fundo / Pivô Concluído)**
  4. Setup Trend ativo $\to$ **🟢 COMPRA RECOMENDADA (Seguidor de Tendência)**
  5. Topo esticado com sobrecompra $\to$ **🟡 AGUARDAR: RISCO DE EXAUSTÃO NO TOPO ANUAL**
  6. $\text{Preço} < \text{SMA}_{200}$ sem reversão $\to$ **🔴 NÃO COMPRAR (TENDÊNCIA DE BAIXA / FACA CAINDO)**
  7. Tendência sem retração $\to$ **🟡 AGUARDAR PULLBACK**
  8. Sem setup confluente $\to$ **🟡 AGUARDAR (SEM SETUP CONFLUENTE NO MOMENTO)**

---

### 3.5. Gestão de Risco e Position Sizing (`core/risk.py`)
* **Modelo:** Risco fixo percentual por operação ($R_{pct} = 2\%$ do patrimônio total).
* **Fórmula do Lote Sugerido:**
  $$\text{Lote} = \left\lfloor \frac{\text{Capital Total} \times R_{pct} \times M_{regime}}{\text{Preço de Entrada} - \text{Stop Loss}} \right\rfloor$$
* **Arredondamento:** Ajustado automaticamente para lotes padrão de 100 ações ou fracionário.
* **Teto Máximo por Posição:** Nenhuma posição pode exceder **25% do capital líquido total**.

---

### 3.6. Auditoria de Travas de Baixa e Opções (`core/risk.py`)
Audita matematicamente estruturas com opções propostas por bancos ou corretoras:
* Modos: `BEAR_PUT` (Trava de Baixa com Put) e `BEAR_CALL` (Trava de Baixa com Call).
* Métricas: Ganho máximo, perda máxima, break-even, assimetria risco/retorno e **Taxa de Acerto Mínima Necessária** ($P_{min} = \frac{\text{Perda Máx}}{\text{Ganho Máx} + \text{Perda Máx}}$).
* Tag de alerta: **🚨 ARMADILHA PARA O VAREJO** se $P_{min} > 60\%$ ou assimetria risco/retorno desfavorável.

---

### 3.7. Realização Parcial (Scale-Out) e Trailing para o Lucro (`ledger/portfolio.py` & `alerts/price_watcher.py`)

Projetado para eliminar 100% do risco da operação ao atingir a primeira meta e deixar os lucros correrem:

1. **Mecânica de Scale-Out:**
   * **Gatilho de Entrada / TP1:** Alvo parcial onde se realiza 50% (ou quantidade parametrizada) da posição.
   * **Preservação de Custo Médio:** A venda parcial liquida proporcionalmente o custo total, mantendo o Preço Médio (PM) unitário original inalterado para as ações remanescentes (conforme IN RFB 1.585/2015).
   * **Elevação de Stop Loss (Trailing para Breakeven/Lucro):** O stop das ações restantes é elevado obrigatoriamente para um patamar $\ge \text{PM}$.
2. **Fórmula do Lucro Mínimo Garantido (Pior Caso):**
   $$\text{PnL Garantido} = (\text{Preço Parcial} - \text{PM}) \times Q_{parcial} + [(\text{Novo Stop} - \text{PM}) \times Q_{restante}]$$
   Se $\text{Novo Stop} > \text{PM}$, o trade fica matematicamente blindado contra perdas financeiras.
3. **Roteiro Anti-Erro para Home Broker:**
   Gera 3 passos sequenciais determinísticos para evitar venda a descoberto acidental:
   * **Passo 1:** Cancelar o Stop antigo da quantidade total;
   * **Passo 2:** Vender a quantidade da parcial a mercado (embolsando o lucro);
   * **Passo 3:** Cadastrar o Novo Stop para a quantidade restante.
4. **Monitor Intradiário de Preços (`alerts/price_watcher.py`):**
   Loop configurável que monitora a cotação a cada $N$ segundos durante o pregão, disparando alertas push no macOS e no Telegram com log anti-duplicação (`AlertLog`).

---

### 3.8. Scanner Concorrente de Alta Performance (`core/screener.py`)
Para contornar o gargalo da ingestão serial de 86+ ativos via Yahoo Finance:
* **Mecanismo:** `concurrent.futures.ThreadPoolExecutor` com dimensionamento dinâmico de workers (`min(12, max(2, len(tickers)))`).
* **Performance:** Redução do tempo de varredura completa de **~80 segundos para ~4.8 segundos**.
* **Thread-Safety:** Coleta e consolidação de resultados centralizada na thread principal com atualização atômica da barra de progresso do `rich`.

---

### 3.9. Engenharia de Risco Setorial, Macro-Clusters e Mitigação de Correlação Cruzada (`data/sectors.py` & `core/risk.py`)

Projetado para eliminar a **vulnerabilidade de perdas em cadeia por sobreposição oculta de fatores de risco** (como a aposta simultânea em Banco do Brasil e ações agrícolas):

#### A. Formalização dos Macro-Clusters de Risco
Cada ativo $A_i$ do universo B3 é formalmente mapeado para uma tupla:
$$\text{Perfil}(A_i) = \langle \text{Setor}_i, \text{Subsetor}_i, \mathcal{C}_i, \text{NotaRisco}_i \rangle$$
Onde $\mathcal{C}_i \subset \{\text{AGRO}, \text{OIL\_GAS}, \text{METALS}, \text{REAL\_ESTATE}, \text{RETAIL}, \text{BANKS}, \text{UTILITIES}, \dots\}$ representa o conjunto de fatores de choque sistêmico aos quais o ativo é exposto.

#### B. Tratamento de Correlação Estrutural Cruzada: Caso `BBAS3`
* **Realidade Econômica:** Embora `BBAS3` pertença ao setor `Financeiro/Bancos`, detém mais de **50% do mercado de crédito rural** do Brasil e $>35\%$ de sua carteira de empréstimos total atrelada a produtores agrícolas.
* **Mapeamento:** `BBAS3` recebe simultaneamente $\mathcal{C}_{BBAS3} = \{\text{FINANCEIRO\_BANCOS}, \text{AGRONEGOCIO}\}$.
* **Regra de Bloqueio/Alerta:** Se a carteira já possuir qualquer ativo agrícola ($\text{AGRO} \in \mathcal{C}_k$), uma nova entrada em `BBAS3` (ou vice-versa) é classificada como **conflito de alta severidade (`HIGH`)**, impedindo a ilusão de diversificação entre banco e agronegócio.

#### C. Limites Prudenciais e Métricas de Diversificação
1. **Teto Setorial:**
   $$E_{setor} = \frac{\sum_{j \in \text{Setor}} \text{Custo}_j}{\text{Capital Base}} \le 35\%$$
2. **Limite de Ativos por Macro-Cluster:**
   $$N_{cluster} \le 1 \quad (\text{Teto máximo de 1 operação ativa por fator de choque})$$
3. **Score de Diversificação da Carteira ($S_{div} \in [10, 100]$):**
   $$S_{div} = 100 - 25 \times (\text{Violações de Teto Setorial}) - 15 \times (\text{Sobreposições de Cluster})$$
   * $S_{div} \ge 80$: Carteira Descorrelacionada e Robusta.
   * $60 \le S_{div} < 80$: Carteira Moderada (Atenção a sobreposições).
   * $S_{div} < 60$: Carteira Crítica (Vulnerável a choques macro).

#### D. Algoritmo de Seleção Anti-Cluster (`filter_diversified_signals`)
Ao selecionar as oportunidades de compra (Top 3 matinal ou sugestões no radar):
1. Descarta ativos que apresentem $\text{Interseção}(\mathcal{C}_{candidato}, \mathcal{C}_{carteira}) \ne \emptyset$ de alta severidade.
2. Na cesta de recomendações resultantes, garante que:
   $$\forall i, j \in \text{Cesta}, i \ne j \implies \text{Setor}_i \ne \text{Setor}_j \land \text{Correl}(\mathcal{C}_i, \mathcal{C}_j) = \text{False}$$
Assegurando que o investidor nunca receba 2 ou 3 recomendações do mesmo setor no mesmo dia.

#### E. Verificação Reativa Pré-Ordem (`check_sector_and_cluster_conflict`)
Executada em tempo real pelo Chat, pela Boleta Web (`app.py`) e pela CLI (`b3pilot buy`), gerando feedback visual imediato antes da confirmação da ordem no banco de dados.

---

## 4. Especificações do Livro-Razão e Fiscalidade (`ledger/`)

### 4.1. Esquema Relacional de Dados (`ledger/db.py`)
Banco de dados relacional SQLite (`portfolio.db`) gerenciado via SQLAlchemy ORM:
* **`transactions`:** Histórico imutável de ordens (`id`, `date`, `ticker`, `type [BUY/SELL]`, `quantity`, `price`, `fees`, `total_value`, `realized_pnl`, `strategy`, `notes`, `is_simulated`).
* **`positions`:** Custódia consolidada em aberto (`id`, `ticker`, `quantity`, `average_price`, `total_cost`, `stop_loss`, `take_profit`, `trailing_stop`, `partial_target`, `partial_quantity`, `new_stop_after_partial`, `is_partial_executed`, `strategy`, `entry_date`, `is_simulated`).
* **`monthly_tax_records`:** Apuração fiscal mensal (`id`, `year_month`, `total_sales`, `is_exempt`, `gross_profit`, `gross_loss`, `net_profit_month`, `previous_losses_deducted`, `taxable_profit`, `irrf_withheld`, `final_darf_due`, `accumulated_loss_carried_over`).
* **`dividend_records`:** Histórico de proventos creditados.
* **`alert_logs`:** Registro de disparos de notificações intradiárias para prevenção de alertas duplicados.

### 4.2. Apuração Tributária Conforme Legislação (`ledger/taxes.py`)
* **Preço Médio Ponderado:** Recalculado a cada compra incluindo taxas de corretagem e emolumentos da B3:
  $$\text{PM}_{novo} = \frac{(\text{PM}_{antigo} \times Q_{antiga}) + (\text{Preço}_{compra} \times Q_{compra} + \text{Taxas})}{Q_{antiga} + Q_{compra}}$$
* **Isenção de R$ 20.000/Mês:** Isenção sobre ganho de capital se o volume total vendido no mês civil for $\le \text{R\$\ 20.000,00}$ (Art. 59 da IN RFB nº 1.585/2015).
* **Compensação de Prejuízos:** Abatimento automático de perdas líquidas acumuladas de meses anteriores antes da aplicação da alíquota.
* **Alíquota e Recolhimento:** 15% sobre o ganho líquido tributável de Swing Trade de ações, deduzindo o IRRF retido na fonte (0,005%), fornecendo o valor exato a pagar no **Código de Receita 6015**.

---

## 5. Especificações de Interface e Usabilidade

### 5.1. Dashboard Web Streamlit (`web/app.py`)
* **Identidade Visual:** Modo Claro (Clean), fontes de sistema (San Francisco, Segoe UI, Roboto), espaçamentos WCAG 2.2 AA.
* **Páginas Operacionais:**
  1. `📊 Visão Geral da Carteira`: Métricas de patrimônio, P&L a mercado, tabela de posições enriquecida com Setor e Segmento, **Painel de Radiografia Setorial** (gráfico Donut de setores, barras de macro-clusters e Score de Diversificação) e assistente de **Scale-Out**.
  2. `💬 Assistente & Chat Operacional`: Chat conversacional com vereditos pré-trade, **alerta preventivo de concentração setorial** caso o usuário consulte ativos correlacionados à custódia, e simulação determinística de parciais.
  3. `🎯 Radar de Oportunidades & Proventos`: Scanner de confluência com colunas Setor, Segmento, Fator de Risco Macro e Status de Diversificação com a Carteira, com **filtro por Setor da B3** e toggle de segurança para **ocultar ativos correlacionados à custódia**.
  4. `🛡️ Auditoria de Travas de Baixa & Opções`: Simulador de assimetria de estruturas de opções.
  5. `📈 Análise Gráfica & Variações (1D a 10A)`: Gráficos de Candlestick com médias móveis e tabela de retornos de 1D a 10 anos.
  6. `📚 Guia dos Setups & Estratégias`: Manual técnico interativo.
  7. `📜 Histórico & Performance`: Registro completo com opção de estorno de transações acidentais.
  8. `📑 Gestão Fiscal & DARF`: Extrato tributário detalhado e dados da DARF 6015.
  9. `➕ Registrar Ordem`: Boleta reativa com busca de cotação, sugestão de lote, alvos parciais (TP1) e **auditoria em tempo real de colisão com setores e clusters da carteira**.

---

### 5.2. CLI Nativo (`cli.py`)

| Comando | Descrição |
| :--- | :--- |
| `b3pilot status` | Mostra custódia, setor, cluster, rentabilidade a mercado, **Score de Diversificação (0 a 100)** e alertas de concentração setorial. |
| `b3pilot scan` | Executa o scanner de confluência com Range de 52 Semanas e metadados setoriais. |
| `b3pilot portfolio` | Extrato resumido das posições abertas. |
| `b3pilot exits` | Audita disparos de Stop Loss, Alvo, Trailing Stop, Time-Stop e Alvos Parciais. |
| `b3pilot partial-sale <TICKER> <QTD> <PRECO> [--new-stop VALOR]` | Executa venda parcial, eleva o stop das remanescentes e gera roteiro para o Home Broker. |
| `b3pilot watch [--interval 300]` | Monitor contínuo intradiário com alertas no Telegram e no macOS. |
| `b3pilot ask "<pergunta>"` | Consulta o Assistente Operacional (com verificação de risco de correlação) ou simula parciais direto no terminal. |
| `b3pilot taxes --month AAAA-MM` | Apura o imposto de renda e calcula a DARF 6015. |
| `b3pilot dividends` | Calendário de próximas Datas COM de dividendos e JCP. |
| `b3pilot buy <TICKER> <QTD> <PRECO> [--tp1 X --tp1-qty Y --new-stop-after-partial Z]` | Registra compra de ações com **auditoria automática de conflito de cluster/setor contra a carteira**. |
| `b3pilot sell <TICKER> <QTD> <PRECO> [--simulated]` | Registra a venda e liquida posição na custódia (Real ou Simulada). |
| `b3pilot audit-trava` | Audita assimetria risco/retorno de travas com opções. |
| `b3pilot web` | Inicia o servidor visual Streamlit na porta 8501. |

---

## 6. Qualidade de Software e Testes Automatizados

O sistema possui uma suíte de testes com **35 testes unitários automatizados** rodando via `pytest`:

* `tests/test_sector_correlation.py`: Mapeamento setorial B3, correlações cruzadas de risco rural (BBAS3 + empresas agrícolas), auditoria de conflito de clusters, cálculo do Score de Diversificação e algoritmo de seleção anti-cluster.
* `tests/test_chat.py`: Extração de tickers, vereditos de compra/venda/espera, alertas de sobreposição setorial, respostas a stops rompidos e simulação de parcial.
* `tests/test_scale_out.py`: Execução de venda parcial, cálculo de pior caso/lucro garantido, preservação de Preço Médio e detecção em saídas.
* `tests/test_core.py`: Indicadores técnicos, métricas de 52 semanas, setups IFR2, Trend, Retomada de Fundo (Pivôs) e saídas.
* `tests/test_risk_regime.py`: Transições de regimes do Ibovespa (Bull, Correction, Bear e Pânico cumulativo semanal) e dimensionamento de lote (2%).
* `tests/test_simulation.py`: Coexistência de posições Reais vs. Simuladas e isolamento de banco.
* `tests/test_taxes.py`: Preço médio ponderado com taxas, isenção de R$ 20k, compensação de prejuízos e DARF 15%.
