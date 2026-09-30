# Plano de Implementação: Correção de Ordens, Preenchimento Dinâmico e Navegação Integrada

Este plano detalha o diagnóstico do registro quádruplo de AURE3, a correção do banco de dados, e as duas integrações de usabilidade solicitadas no **B3 Ações Pilot**.

---

## 1. Diagnóstico: Por que AURE3 registrou 40 ações em vez de 10?

No banco de dados SQLite (`portfolio.db`), identificamos 4 transações de compra de 10 ações registradas em sequência rápida:
1. **13:28:34:** 10 ações a R$ 30,00 (valor default do formulário antigo)
2. **13:28:38 (4s depois):** 10 ações a R$ 30,00 (segundo clique ou reenvio)
3. **13:28:55:** 10 ações a R$ 12,83 (após ajuste manual do preço)
4. **13:29:38:** 10 ações a R$ 12,83 (novo clique de confirmação)

Como o formulário do Streamlit não limpava após a submissão nem continha trava de idempotência contra cliques repetidos, cada clique somou 10 ações na custódia:
$$10 + 10 + 10 + 10 = 40 \text{ ações (PM R\$ 21,56)}$$

---

## 2. Mudanças Propostas

### A. Reconciliação do Banco de Dados e Proteção contra Duplicidade

#### [MODIFY] [portfolio.db](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/portfolio.db)
- Executar reconciliação na tabela `transactions` para remover as transações duplicadas e com valor incorreto (IDs 1, 2 e 4), mantendo estritamente a compra real de **10 ações a R$ 12,83** (taxa R$ 1,50).
- Atualizar a tabela `positions` para:
  - Quantidade: **10 ações**
  - Custo total: **R$ 129,80**
  - Preço Médio: **R$ 12,98**
  - Stop Loss: **R$ 11,00**
  - Take Profit: **R$ 13,50**

#### [MODIFY] [app.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/web/app.py) & [portfolio.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/ledger/portfolio.py)
- **Token de Idempotência / Trava de Duplo Envio:** Adicionar verificação em `st.session_state` e timestamp no envio de ordens. Se o usuário clicar repetidamente em menos de 5 segundos para a mesma ação, o sistema ignora o segundo clique e exibe aviso de que a ordem já foi processada.
- **Gerenciador de Cancelamento no Histórico:** Na aba "📜 Histórico & Performance", adicionar uma opção de **Excluir Transação Recente**, permitindo ao usuário desfazer lançamentos acidentais diretamente pela interface visual com recálculo automático da posição.

---

### B. Registro de Ordem Reativo: Cotação Atual ao Digitar o Ticker

#### [MODIFY] [app.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/web/app.py)
- Mover a seleção do Ticker para fora do bloco rígido do formulário, permitindo renderização reativa em tempo real:
  - Ao digitar o ticker (ex: `AURE3`, `PETR4`, `VALE3`) ou clicar nele:
    1. O sistema dispara a consulta à cotação de mercado mais recente via `fetch_latest_price(ticker)`.
    2. Calcula automaticamente a volatilidade ATR(14) e sugere:
       - **Preço de Execução:** Cotação real de mercado (ex: R$ 12,83).
       - **Stop Loss Sugerido:** Baseado em suporte / $2 \times \text{ATR}$ (ex: R$ 11,55).
       - **Take Profit Sugerido:** Relação 2.5R de retorno (ex: R$ 16,00).
       - **Lote Recomendado:** Dimensionamento de posição (2% do capital).
    3. Exibe card com resumo do ativo: última cotação, variação diária e alerta se o usuário já possui custódia daquele ativo (mostrando o PM atual e novo PM simulado caso compre mais).

---

### C. Integração Direta: Radar de Oportunidades $\to$ Análise Gráfica & Variações

#### [MODIFY] [app.py](file:///Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/b3pilot/web/app.py)
- Vincular a navegação do Streamlit ao `st.session_state["nav_menu"]` e `st.session_state["analysis_ticker"]`.
- No **Radar de Oportunidades**:
  - Habilitar seleção de linha interativa no `st.dataframe` (`on_select="rerun"`, `selection_mode="single-row"`). Ao clicar na linha da ação, o app migra automaticamente para a aba "📈 Análise Gráfica & Variações".
  - Adicionar cards visuais de acesso rápido abaixo da tabela para cada oportunidade encontrada, com dois botões de 1 clique:
    - `[📈 Ver Gráfico & Variações]`: Abre imediatamente a aba gráfica daquela ação (1D a 10A).
    - `[🛒 Comprar no Radar]`: Abre a aba de registro de ordem já pré-preenchida com o ticker, cotação e lote recomendados.
- Na aba **Análise Gráfica & Variações**:
  - Inicializar o campo de busca de ticker lendo `st.session_state.get("analysis_ticker", "WEGE3")`, garantindo que o gráfico do papel clicado seja renderizado imediatamente sem precisar digitar novamente.

---

## 3. Plano de Verificação

### Testes Automatizados
- Executar suíte de testes com `./.venv/bin/pytest tests/` para garantir que as alterações no ledger e na custódia continuam 100% íntegras.

### Verificação Manual
1. Inspecionar o banco `portfolio.db` via SQLite para confirmar que AURE3 possui exatamente 10 ações a R$ 12,83.
2. Acessar `http://localhost:8501`, digitar um ticker na aba "Registrar Ordem" e validar se a cotação a mercado é carregada automaticamente.
3. Ir ao Radar de Oportunidades, clicar em uma oportunidade e validar a transição imediata para o gráfico correspondente.
