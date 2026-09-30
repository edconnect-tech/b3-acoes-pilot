# Plano de Implementação: Expansões Institucionais de Risco e Arquitetura

Este plano de implementação operacionaliza as 4 expansões quantitativas aprovadas pelo usuário para sanar as vulnerabilidades do `b3-acoes-pilot` identificadas na auditoria técnica, além de estruturar o módulo e a análise crítica sobre a recomendação bancária de "Trava de Baixa" em `MCDC34`.

---

## Análise Paralela: Travas de Baixa Recomendadas por Bancos (MCDC34)

### 1. Por que o Banco está Recomendando Trava de Baixa em MCDC34?
1. **Contexto Fundamentalista do McDonald's (MCD / MCDC34):**
   * O McDonald's enfrenta desaceleração de tráfego de clientes de média/baixa renda, forte guerra de preços ("value meals" nos EUA) e margens pressionadas. Em termos gráficos, o ativo testou zonas de resistência técnica.
2. **O Mecanismo Oculto dos Bancos/Corretoras:**
   * **Margem e Spread de Balcão:** Ao recomendar travas estruturadas de opções em "1 clique" pelo aplicativo, a mesa de derivativos do banco atua como contraparte ou precifica o spread das pontas com margem generosa embutida. A corretagem aparente pode ser "zero", mas o spread de volatilidade implícita e deságio é capturado pelo banco.
   * **Desova de Risco da Tesouraria:** Mesas de opções frequentemente precisam zerar riscos direcionais de posições de grandes clientes institucionais; empacotar a ponta oposta como "oportunidade para o varejo" equilibra o livro da tesouraria do banco.
3. **Vale a pena o risco para o investidor pessoa física?**
   * **Geralmente NÃO vale a pena** pelas seguintes razões quantitativas:
     * **Assimetria Desfavorável:** A maioria dessas travas oferecidas em apps possui perda máxima de 100% do capital alocado na estrutura (se o papel subir ou ficar de lado) para um ganho máximo de 30% a 50%. Você arrisca R$ 1.000 para ganhar R$ 300 a R$ 500.
     * **Tributação Punição:** Opções **não possuem a isenção de R$ 20.000/mês** da Receita Federal. Qualquer ganho sofre 15% de IR obrigatório via DARF.
     * **Falta de Liquidez do BDR:** MCDC34 tem baixíssima liquidez de opções na B3 se comparado a PETR4 ou VALE3, gerando spreads cruéis na montagem e desmontagem.

### 2. Como isso pode ser indicado no seu sistema de forma vantajosa?
Em vez de copiar produtos de balcão de bancos, o `b3-acoes-pilot` incorporará:
1. **Radar de Sinais de Baixa / Proteção de Carteira (Bear Setup):** Identifica papéis esticados perdendo suporte ou cruzando médias para baixo (`Close < EMA9 < EMA21` com IBOV fraco), sinalizando **venda/realização de lucros** ou **hedging**.
2. **Calculadora e Auditor de Assimetria de Travas:** Um módulo que permite simular uma trava de opções e calcular seu Risco/Retorno real. Se o ganho projetado for menor que 1.5x o risco ou se não houver liquidez suficiente, o sistema emite um alerta explícito: **"⚠️ Armadilha de Derivativos de Varejo"**.

---

## Proposta de Mudanças Arquiteturais no `b3-acoes-pilot`

### Componente 1: Regime de Mercado e Macro Filter

#### [NEW] [regime.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/core/regime.py)
* Baixa dados do IBOVESPA (`^BVSP`) e classifica o mercado em:
  * `BULL`: Ibovespa > SMA 200 e EMA 9 > EMA 21. Sinais de compra liberados com 100% de exposição.
  * `CORRECTION`: Ibovespa > SMA 200, porém EMA 9 < EMA 21. Sinais de Momentum suspensos; IFR2 liberado com cautela.
  * `BEAR`: Ibovespa < SMA 200. Compras de Momentum bloqueadas; IFR2 apenas em sobrevenda extrema ($\le 5.0$) com tamanho de lote reduzido (50%).
  * `PANIC`: Queda intradiária do IBOV $> 2.5\%$. Bloqueio total de novas compras no dia.

---

### Componente 2: Liquidez Financeira Real (ADTV em R$) e Sanitização

#### [MODIFY] [universe.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/data/universe.py)
* Correção cadastral de tickers: trocar `JBSS32.SA` por `JBSS3.SA` e remover tickers descontinuados ou inconsistentes.

#### [MODIFY] [b3_feed.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/data/b3_feed.py)
* Inclusão do cálculo de **ADTV Financeiro Médio de 21 pregões** ($\text{ADTV}_{21} = \text{Média}(\text{Volume} \times \text{Close})$).
* Descarte imediato de qualquer ativo que possua $\text{ADTV}_{21} < \text{R\$ 5.000.000,00}$ para evitar ativos ilíquidos.

---

### Componente 3: Dimensionamento de Posição (Position Sizing)

#### [NEW] [risk.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/core/risk.py)
* Implementação do cálculo de lote por paridade de risco financeiro (2% do capital):
  $$\text{Risco em R\$} = \text{Capital Total} \times 0.02$$
  $$\text{Lote Base} = \left\lfloor \frac{\text{Risco em R\$}}{\text{Preço de Entrada} - \text{Stop Loss}} \right\rfloor$$
* Aplicação de teto máximo de alocação por ativo (máximo 25% do capital total em um único ativo para evitar concentração).
* Arredondamento para lotes padrão (múltiplos de 100) ou lote fracionário conforme o capital disponível.
* Simulador e Auditor de Operações Estruturadas (Travas de Baixa/Alta), calculando relação ganho/perda e viabilidade de opções.

---

### Componente 4: Refinamento dos Setups e Saída na Data COM

#### [MODIFY] [strategies.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/core/strategies.py)
* **IFR2:** Remoção do Stop Loss curto de $2 \times \text{ATR}$ que degradava o Win Rate. O setup passa a adotar Stop Catastrófico (8% a 10%) e foco em saída no alvo de máxima de 2 dias ou Time-Stop estrito de 5 pregões.
* **Seguidor de Tendência:** Eliminação do gatilho esticado `Close > High_anterior`. Exigência de retração (*pullback*) próxima às médias (preço tocando a zona entre EMA 9 e EMA 21) com retomada de volume.

#### [MODIFY] [exits.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/core/exits.py)
* Criação do gatilho de saída urgente `SELL_DATA_COM`: se uma posição de captura de proventos atingir a sua Data COM, o sistema gera alerta de venda imediata no leilão de fechamento para embolsar a valorização pré-anúncio e **evitar o desconto obrigatório na Data EX**.

#### [MODIFY] [morning_job.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/alerts/morning_job.py)
* Integração do Regime de Mercado no alerta matinal.
* Recomendação do número de ações e capital estimado a investir por trade (Position Sizing).
* Guardrail de Gap: aviso de descarte se o papel abrir com gap superior a $0.5 \times \text{ATR}$.

---

### Componente 5: Interface Web Streamlit e Dashboard

#### [MODIFY] [app.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/web/app.py)
* Inclusão do **Badge de Regime de Mercado (IBOVESPA)** no topo da página (Bull Market, Correção ou Bear Market).
* Adição da **Calculadora de Lote e Dimensionamento de Risco** no Radar de Oportunidades e no formulário de compra.
* Nova aba/seção dedicada à **Auditoria de Derivativos e Operações Estruturadas (Travas)**, permitindo auditar recomendações de bancos como a trava de baixa de `MCDC34`.

---

## Plano de Verificação

### Testes Automatizados
* Executar a suíte de testes com `pytest tests/`:
  - `tests/test_core.py`
  - `tests/test_taxes.py`
  - Criar `tests/test_risk_regime.py` validando o classificador de regime de mercado e o cálculo matemático de Position Sizing.

### Verificação Manual
1. Executar o CLI: `b3pilot scan --category top20` e validar a exibição do Regime do Ibovespa e do lote recomendado.
2. Acessar o Streamlit em `http://localhost:8501` e verificar:
   - Status do IBOVESPA em tempo real.
   - Colunas de ADTV financeiro e Lote sugerido na tabela do Radar de Oportunidades.
   - Aba explicativa e auditor de travas de opções.
