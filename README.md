# B3 Ações Pilot 🚀

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-2563eb?logo=python&logoColor=white)](https://www.python.org/)
[![Licença: BSL 1.1](https://img.shields.io/badge/Licen%C3%A7a-BSL%201.1-0f172a)](LICENSE)
[![CI Tests](https://github.com/edconnect-tech/b3-acoes-pilot/actions/workflows/ci.yml/badge.svg)](https://github.com/edconnect-tech/b3-acoes-pilot/actions/workflows/ci.yml)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-EdConnect%20Tecnologia-db2777?logo=githubsponsors)](https://github.com/sponsors/edconnect-tech)
[![Pix CNPJ](https://img.shields.io/badge/Pix%20CNPJ-64.763.482%2F0001--14-059669)](#-apoie-o-desenvolvimento)

Assistente quantitativo autônomo e *local-first* para **Swing Trade**, **Captura de Proventos (Dividendos e JCP na Data COM)** e **Gestão Fiscal na B3 (Bolsa Brasileira)** — desenvolvido pela **[EdConnect Tecnologia](https://edconnect.com.br)**.

O sistema opera de forma determinística combinando **modelos matemáticos em Python** (`pandas`, `pandas_ta`, `numpy`), banco de dados relacional **SQLite**, dashboard interativo em **Streamlit** (Modo Claro / Clean, WCAG 2.2 AA), linha de comando nativa (**CLI Typer/Rich**), rotina de alertas matinais (**Telegram e macOS**) e conectores opcionais com **APIs de IA e CLIs com login nativo (Google Antigravity `agy`, Gemini CLI, Claude Code e Codex)**.

---

## 🏛️ Arquitetura do Sistema

```
b3-acoes-pilot/
├── b3pilot/
│   ├── ai/                     # Conectores multi-provedor de IA (Zero Trust no LLM)
│   │   └── providers.py        # Login OAuth via CLIs (agy/gemini/claude/codex) e APIs REST
│   ├── core/                   # Motores quantitativos, estratégias, risco e regimes
│   │   ├── regime.py           # Gatekeeper de Regime de Mercado (Ibovespa)
│   │   ├── strategies.py       # IFR2, Trend Following, 52W Range e Bear Signals
│   │   ├── dividend_strategy.py# Radar Pré-Data COM e captura de proventos
│   │   ├── risk.py             # Position Sizing determinístico (Risco fixo 2%) e anti-cluster
│   │   ├── exits.py            # Motor de Saídas (Stop Loss, Alvo, Trailing, Time-Stop)
│   │   ├── screener.py         # Scanner unificado multithread com confluência e ranking
│   │   └── chat.py             # Assistente operacional (determinístico + síntese opcional via IA)
│   ├── data/                   # Ingestão de dados de mercado e universo B3
│   │   ├── b3_feed.py          # Cache local em Parquet e downloads via yfinance
│   │   ├── dividends_feed.py   # Rastreamento de proventos e datas de corte
│   │   ├── sectors.py          # Matriz Setorial B3 e Macro-Clusters de Risco
│   │   └── universe.py         # Universos Top B3 (alta liquidez) e Amplo
│   ├── ledger/                 # Livro-razão financeiro, carteira e tributação
│   │   ├── db.py               # Esquema relacional SQLAlchemy (SQLite)
│   │   ├── portfolio.py        # Controle de posições (Reais e Simuladas), parciais e P&L
│   │   └── taxes.py            # Apuração de IRPF, isenção R$ 20k e DARF (Cód. 6015)
│   ├── alerts/                 # Rotina de automação matinal e monitor intradiário
│   │   ├── morning_job.py      # Job diário pré-abertura (09:55 BRT)
│   │   ├── price_watcher.py    # Monitor contínuo de stops, alvos e reversões
│   │   └── notifier.py         # Disparo para Telegram Bot API e Notification Center (macOS)
│   ├── web/                    # Interface visual Streamlit (Modo Claro / Clean)
│   │   └── app.py              # Dashboard, chat com IA, radar, gráficos e gestão fiscal
│   └── cli.py                  # Interface de Linha de Comando (Typer + Rich)
├── scripts/                    # Automação de cron/launchd, skills e seed Paper Trading
├── tests/                      # Suíte de 53 testes unitários automatizados (pytest)
└── portfolio.db                # Banco SQLite local persistente (ignorado pelo Git)
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
* **Filtro de Liquidez Real:** Volume Financeiro Médio Diário dos últimos 21 dias ($\text{ADTV}_{21}$ ≥ R\$ 5.000.000).
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

### 3. Scanner Concorrente de Alta Velocidade (`core/screener.py`) e Range Anual (52 Semanas)
* Processamento paralelo via `ThreadPoolExecutor` com 12 workers concorrentes (varredura de ~86+ ativos em poucos segundos).
* Para evitar comprar ativos esticados no topo do canal anual e selecionar papéis com **ampla pista livre até a resistência**, o sistema calcula:

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
* **A Armadilha:** O investidor adquire ações do Banco do Brasil acreditando estar posicionado no setor bancário defensivo e, simultaneamente, compra ações de empresas agrícolas (`SOJA3`, `SMTO3`, `AGRO3`, `SLCE3`).
* **A Realidade Institucional:** O Banco do Brasil é o maior financiador do agronegócio do país, respondendo por grande parcela do crédito rural nacional. Em quebras de safra ou retração de grãos, inadimplência agrícola e provisões (PDD) do banco aumentam juntos.
* **A Blindagem do B3 Pilot:** O ativo `BBAS3` possui dupla classificação (`FINANCEIRO_BANCOS` e `AGRONEGOCIO`). Qualquer tentativa de sobrepor posições de crédito rural e agronegócio é imediatamente sinalizada ou filtrada.

#### Mapeamento dos Macro-Clusters de Risco da B3

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
1. **Teto Setorial Prudencial:** Máximo de **35% do capital alocado em um único setor**.
2. **Limite de Trades Ativos por Macro-Cluster:** Máximo de **1 operação simultânea por cluster**.
3. **Score de Diversificação (0 a 100):** $\ge 80$ Excelente | $60 - 79$ Moderada | $< 60$ Crítica.
4. **Filtro de Descorrelação no Screener e Morning Job:** As 3 recomendações matinais pertencem a **setores 100% independentes** e não colidem com a custódia em aberto.

---

### 7. Motor de Saídas Contínuo (`core/exits.py`) e Realização Parcial (`ledger/portfolio.py`)
* **Stop Loss Atingido:** Cotação $\le \text{Stop Loss}$ $\rightarrow$ Venda imediata (**Urgência ALTA**).
* **Alvo de Realização Parcial (TP1):** Venda de 50% ao atingir TP1 e subida do stop das ações remanescentes para garantir lucro no pior caso:
  $$\text{PnL Mínimo} = \text{Lucro da Parcial} + [(\text{Novo Stop} - \text{Preço Médio}) \times \text{Qtd Restante}]$$
* **Alvo Final (Take Profit), Trailing Stop e Time-Stop (5º pregão no IFR2).**

---

## 🤖 Conectores de IA (APIs & Login Google Antigravity `agy`)

O **B3 Ações Pilot** aplica arquitetura **Zero Trust no LLM**: todo cálculo numérico (indicadores, stops, tamanho de lote e apuração fiscal de DARF) é executado em **Python determinístico 64-bit**. O conector de IA é **opcional** e atua como copiloto interpretativo ancorado exclusivamente no relatório calculado pelo sistema.

### Provedores Suportados (`b3pilot/ai/providers.py`)

| ID | Provedor | Autenticação | Caso de Uso Ideal |
| :--- | :--- | :--- | :--- |
| `deterministic` | **Local Determinístico (Python)** | Sem login / Sem API Key | Padrão: 100% offline/local, latência mínima |
| `agy` | **Google Antigravity CLI (`agy`)** | **Login Google nativo (OAuth)** | Usar sua assinatura/conta Google no Antigravity sem gerar API Key |
| `gemini_cli` | **Google Gemini CLI (`gemini`)** | **Login Google nativo (OAuth)** | Terminal autenticado com conta Google |
| `claude_cli` | **Claude Code CLI (`claude`)** | **Login Anthropic nativo** | Terminal autenticado via `claude login` |
| `codex_cli` | **OpenAI Codex CLI (`codex`)** | **Login OpenAI/ChatGPT nativo** | Terminal autenticado via `codex login` |
| `gemini` | **Google Gemini API (AI Studio)** | `GEMINI_API_KEY` | Nuvem rápida e gratuita/econômica (`gemini-2.5-flash`) |
| `openai` | **OpenAI API** | `OPENAI_API_KEY` | Modelos `gpt-4o-mini`, `gpt-4o`, etc. |
| `anthropic` | **Anthropic Claude API** | `ANTHROPIC_API_KEY` | Modelos Claude Sonnet/Opus |
| `openrouter` | **OpenRouter** | `OPENROUTER_API_KEY` | Acesso unificado a 200+ modelos |
| `groq` | **Groq Cloud** | `GROQ_API_KEY` | Inferência ultra-rápida (Llama 3.3, etc.) |
| `deepseek` | **DeepSeek API** | `DEEPSEEK_API_KEY` | Custo reduzido (`deepseek-chat`) |
| `ollama` | **Ollama Local** | Sem chave (`localhost:11434`) | Privacidade absoluta rodando modelos locais |
| `openai_compatible`| **Endpoint OpenAI-Compatible** | `AI_BASE_URL` (+ `AI_API_KEY`) | LM Studio, vLLM, Azure ou gateways corporativos |

### Opção 1 — Login com Conta Google via Antigravity (`agy`) ou CLIs (Sem API Key)
Se você já utiliza o **Google Antigravity (`agy`)**, Gemini CLI, Claude Code ou Codex:
1. Autentique-se uma única vez no terminal com sua conta:
   ```bash
   # Google Antigravity (abre o login Google na primeira execução)
   agy

   # Ou alternativas:
   # gemini          # Login Google Gemini CLI
   # claude login    # Login Anthropic Claude Code
   # codex login     # Login OpenAI Codex CLI
   ```
2. Verifique os conectores detectados e teste a conexão:
   ```bash
   b3pilot ai-status
   b3pilot ai-test --provider agy
   ```
3. Consulte o assistente usando sua conta conectada (ou selecione **`Google Antigravity CLI (agy)`** dentro do expander **"🤖 Conector de IA"** no Dashboard Web):
   ```bash
   b3pilot ask --ai -p agy "Posso comprar PETR4 hoje considerando minha carteira?"
   ```

### Opção 2 — Conectando via API Key (Gemini, OpenAI, Anthropic, OpenRouter, Groq, DeepSeek) ou Ollama
Edite apenas o conector desejado no arquivo `.env` (ou informe a chave somente para a sessão no Dashboard Web):
```env
# Exemplo com seleção automática (prioriza agy -> APIs configuradas -> CLIs -> deterministic)
AI_PROVIDER=auto

# Configure somente a chave do provedor escolhido:
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
GROQ_API_KEY=
DEEPSEEK_API_KEY=

# Ou Ollama 100% local:
# AI_PROVIDER=ollama
# AI_MODEL=llama3.2
# OLLAMA_BASE_URL=http://localhost:11434
```

---

## 🚀 Instalação e Configuração

### Requisitos
* **Python 3.12 ou superior**
* **Git**
* Sistema Operacional: **macOS**, **Linux** ou **Windows 10/11 (PowerShell / WSL)**

### Passo a Passo — macOS e Linux
```bash
# 1. Clone o repositório oficial da EdConnect Tecnologia
git clone https://github.com/edconnect-tech/b3-acoes-pilot.git
cd b3-acoes-pilot

# 2. Crie e ative o ambiente virtual isolado
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale o pacote e suas dependências
pip install -e .

# 4. Crie seu arquivo de configuração local (.env nunca é versionado)
cp .env.example .env

# 5. Valide a instalação rodando os testes unitários
pytest -v

# 6. Abra o Dashboard Web ou use a CLI
b3pilot web
```

### Passo a Passo — Windows (PowerShell)
```powershell
# 1. Clone o repositório
git clone https://github.com/edconnect-tech/b3-acoes-pilot.git
cd b3-acoes-pilot

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instale o pacote
pip install -e .

# 4. Copie as variáveis de ambiente
Copy-Item .env.example .env

# 5. Execute os testes e abra o dashboard
pytest -v
b3pilot web
```

> **💡 Dica para testar com dados fictícios (Paper Trading):** antes de cadastrar sua carteira real ou para capturar prints seguros, popule apenas o **Laboratório Simulado** (`is_simulated=True`) sem tocar em dados reais ou tributos:
> ```bash
> python scripts/seed_demo_portfolio.py --reset
> ```

---

## 📲 Como Configurar Mensagens e Alertas no Telegram

O **B3 Ações Pilot** envia alertas matinais às **09:55 BRT** (antes da abertura da B3) e avisos intradiários de **Stop Loss**, **Alvo Parcial (com roteiro para o Home Broker)** e **Take Profit** diretamente no seu celular via Telegram.

### Passo 1 — Criar seu Bot no `@BotFather`
1. Abra o Telegram e pesquise por **`@BotFather`** (verificado com selo azul).
2. Envie o comando `/newbot`.
3. Escolha um nome de exibição (ex.: `Meu B3 Pilot`) e um username terminado em `bot` (ex.: `meu_b3pilot_bot`).
4. O BotFather responderá com um **HTTP API Token** no formato `123456789:AAH...`. Esse é o seu `TELEGRAM_BOT_TOKEN`.

### Passo 2 — Descobrir o seu `TELEGRAM_CHAT_ID`
1. Clique no link do seu novo bot enviado pelo BotFather e clique em **Iniciar** (ou envie `/start` para ele). **Esse passo é obrigatório** — bots no Telegram não podem enviar mensagens antes de você iniciar a conversa.
2. Abra no navegador (substituindo `<SEU_TOKEN>` pelo token copiado):
   ```text
   https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
   ```
   *(Alternativa rápida: envie qualquer mensagem para o bot `@userinfobot` no Telegram para ver seu ID numérico instantaneamente).*
3. No JSON retornado em `getUpdates`, localize o número em `"chat": {"id": 123456789, ...}`. Esse número é o seu `TELEGRAM_CHAT_ID`.

### Passo 3 — Salvar no `.env` e Testar o Envio
Edite o arquivo `.env` na raiz do projeto:
```env
TELEGRAM_BOT_TOKEN=123456789:AAH_seu_token_aqui
TELEGRAM_CHAT_ID=987654321
```
Execute o comando de validação:
```bash
b3pilot test-telegram
```
Se estiver tudo correto, você receberá na hora a mensagem `🚀 B3 Ações Pilot: Conexão com Telegram funcionando com sucesso!`.

### Passo 4 — Agendar Alertas Automáticos (09:55 BRT) e Monitor Intradiário
* **No macOS (via `launchd` nativo):**
  ```bash
  ./scripts/setup_cron.sh
  launchctl load ~/Library/LaunchAgents/com.b3pilot.morning.plist
  ```
* **No Linux / WSL (`crontab -e`):**
  ```cron
  55 9 * * 1-5 cd /caminho/para/b3-acoes-pilot && ./.venv/bin/b3pilot alert >> /tmp/b3pilot.log 2>&1
  ```
* **Monitor Contínuo durante o Pregão (a cada 5 minutos):**
  ```bash
  b3pilot watch --interval 300
  ```

---

## 🖥️ Funcionalidades e Comandos da CLI (`b3pilot`)

### 1. Interface Web Interativa (Streamlit)
Execute localmente com `b3pilot web`:
* **Estética Clean / Modo Claro (WCAG 2.2 AA)** com fontes nativas do sistema.
* **💬 Assistente & Chat Operacional:** Consulta de setups em tempo real, alerta setorial preventivo, simulador de parciais em linguagem natural e seletor de **Conectores de IA (APIs & Login Google `agy`)**.
* **📊 Dashboard Executivo & Radiografia Setorial:** Patrimônio líquido, P&L, gráfico Donut de setores B3, barras de Macro-Clusters e **Score de Diversificação**.
* **🎯 Radar de Oportunidades & Proventos:** Tabela com notas (0–10), Range 52S, filtro anti-correlação e calendário pré-Data COM.
* **🛡️ Auditoria de Travas de Baixa & Opções:** Diagnóstico matemático de estruturas e proteção contra armadilhas assimétricas.
* **📈 Análise Gráfica & Variações (1D a 10A):** Candlestick com EMA 9/21, SMA 50/200, IFR2, IFR14 e ATR.
* **📑 Gestão Fiscal & DARF:** Preço médio ponderado com taxas, isenção de R$ 20.000/mês (Art. 59 da IN RFB nº 1.585/2015), compensação de prejuízos e DARF **Código 6015 (15%)**.
* **Carteira Real vs. Laboratório Simulado (*Paper Trading*):** Coexistência isolada no SQLite.

### 2. Principais Comandos no Terminal
```bash
# Status completo da carteira, PnL e Score de Diversificação
b3pilot status

# Scanner quantitativo completo ou apenas alta convicção (Score >= 8.0 & R/R >= 2.2)
b3pilot scan
b3pilot scan --high

# Calendário de próximas Datas COM para captura de dividendos e JCP
b3pilot dividends

# Registrar compra com Stop, TP1 (Parcial) e TP2 (Alvo Final)
b3pilot buy PETR4 200 38.50 --strategy TREND --stop 36.20 --tp1 41.50 --target 44.00

# Registrar realização parcial (50%) e elevar Stop Loss
b3pilot partial-sale SOJA3 31 8.60 --new-stop 8.25

# Registrar venda total e apurar status fiscal
b3pilot sell PETR4 200 42.10

# Apuração mensal de imposto de renda e DARF
b3pilot taxes

# Consultar assistente determinístico ou com conector de IA
b3pilot ask "Posso comprar PETR4 agora?"
b3pilot ask --ai -p agy "Analise minha carteira e me diga se há risco setorial"

# Gerenciar conectores de IA e alertas Telegram
b3pilot ai-status
b3pilot ai-test --provider agy
b3pilot test-telegram
b3pilot alert
b3pilot web
```

### 3. Integração Nativa com Skills (`agy` / Claude / Gemini CLI)
Instale a skill automaticamente no seu ambiente local:
```bash
./scripts/install_skill.sh        # Padrão: Antigravity CLI (~/.gemini/config/skills)
./scripts/install_skill.sh --all  # Também instala para Claude Code e Gemini CLI
```

---

## 🧪 Testes Automatizados

O sistema conta com suíte de **53 testes unitários automatizados** garantindo a integridade dos cálculos matemáticos, regras tributárias, blindagem setorial, conectores de IA e isolamento do modo simulado:

```bash
pytest -v
```

Cobertura dos testes:
* `tests/test_ai_connectors.py`: Validação de URLs Zero Trust, proteção contra vazamento de segredos, prioridade de detecção, flags `shell=False` para CLIs (`agy`, `gemini`, `claude`, `codex`), headers REST (`x-goog-api-key` no Gemini, Anthropic, OpenAI/OpenRouter/Groq/DeepSeek, Ollama) e fallback determinístico.
* `tests/test_demo_seed.py`: Seed da carteira fictícia (*Paper Trading*) em 5 setores/clusters distintos, idempotência e proteção Zero Trust contra alteração de custódia real ou registros fiscais.
* `tests/test_sector_correlation.py`: Mapeamento setorial B3, correlação cruzada (`BBAS3` + Agronegócio), Score de Diversificação e filtro anti-cluster.
* `tests/test_chat.py`: Motor conversacional, extração de tickers B3, decisões pré-trade e simulação de realização parcial.
* `tests/test_scale_out.py`: Realização parcial (50%), cálculo de lucro garantido no pior caso e preservação do Preço Médio.
* `tests/test_core.py`: Indicadores técnicos, métricas de 52 semanas, setups IFR2, Trend Following, Retomada de Fundo (Pivôs) e disparos de saída.
* `tests/test_risk_regime.py`: Transições de regimes de mercado e dimensionamento de risco por trade.
* `tests/test_simulation.py`: Isolamento entre posições reais e simuladas no banco SQLite.
* `tests/test_taxes.py`: Preço médio ponderado com corretagem, isenção de R$ 20k, compensação de prejuízos e DARF 15%.

---

## ☕ Apoie o Desenvolvimento

Se o **B3 Ações Pilot** economiza seu tempo com cálculos de Swing Trade, Proventos ou apuração mensal de DARF, considere apoiar a evolução contínua do projeto pela **EdConnect Tecnologia**:

### 🇧🇷 Apoio via Pix (Brasil — CNPJ)
* **Favorecido:** EdConnect Tecnologia Ltda
* **Tipo de Chave:** CNPJ
* **Chave Pix Formatada:** `64.763.482/0001-14`

**Copia e Cola da Chave Pix (somente números):**
```text
64763482000114
```

### 🌍 Apoio via GitHub Sponsors
* Acesse: **[github.com/sponsors/edconnect-tech](https://github.com/sponsors/edconnect-tech)** (ou clique no botão **♥ Sponsor** no topo deste repositório).

---

## ⚖️ Licença (BSL 1.1) e Isenção de Responsabilidade (CVM)

* **Licenciamento (`LICENSE`):** Este software é distribuído em modelo *Source-Available* sob a **[Business Source License 1.1 (BSL 1.1)](LICENSE)** pela **EdConnect Tecnologia Ltda** (`CNPJ 64.763.482/0001-14`).
  * **Uso permitido gratuitamente:** uso pessoal, educacional e operacional próprio (*self-hosted*) para gestão da sua própria carteira e impostos na B3.
  * **Uso restrito:** é vedada a revenda, oferta como serviço hospedado/gerenciado (*SaaS*), sala de sinais paga ou incorporação em produtos comerciais de terceiros sem licença comercial prévia (`ricardo@edconnect.com.br`).
  * **Data de Conversão (*Change Date*):** `2030-11-20`, quando cada versão distribuída converte automaticamente para **GNU GPL v3.0 ou posterior (`GPL-3.0-or-later`)**.
* **Isenção de Responsabilidade (Resolução CVM nº 20):** Este software tem finalidade estritamente analítica, quantitativa e educacional. O uso dos algoritmos, rastreadores de Data COM e sugestões de dimensionamento de risco não constitui recomendação pública de valores mobiliários nem consultoria de investimentos. O usuário é o único responsável pela conferência dos dados em sua corretora, emissão de DARF e execução de suas ordens na B3.
