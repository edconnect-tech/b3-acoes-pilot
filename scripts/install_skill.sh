#!/usr/bin/env bash
# Script para registrar a Skill b3-acoes-pilot no Antigravity CLI (agy)

set -e

DEST_DIR="$HOME/.gemini/config/skills/b3-acoes-pilot"
mkdir -p "$DEST_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cat << 'EOF' > "$DEST_DIR/SKILL.md"
---
name: b3-acoes-pilot
description: |
  Assistente autônomo de Swing Trade, Proventos (Dividendos e JCP na Data COM) e Gestão Fiscal para ações da B3 (Brasil).
  Ative esta skill quando o usuário solicitar:
  - Análise ou situação atual da carteira de ações na B3.
  - Varredura de mercado / scanner de compras (IFR2, Seguidor de Tendência, Momentum).
  - Consulta de calendário de dividendos, JCP e próximas Datas COM.
  - Registro de ordens de compra ou venda de ações.
  - Cálculo de imposto de renda, apuração da isenção de R$ 20.000, compensação de prejuízos e emissão de DARF (Código 6015).
  - Abertura do dashboard visual no navegador.
---

# B3 Ações Pilot (Antigravity agy Native)

Esta skill permite ao agente Antigravity interagir diretamente com o sistema local de Swing Trade e Proventos em /Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot.

## Comandos Operacionais

O executável CLI está em /Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot.

- **Status da Carteira:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot status`
- **Scanner de Compras:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot scan`
- **Calendário de Proventos:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot dividends`
- **Comprar Ação:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot buy TICKER QUANTIDADE PRECO`
- **Vender Ação:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot sell TICKER QUANTIDADE PRECO`
- **Gestão Fiscal e DARF:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot taxes`
- **Rotina Matinal de Alertas:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot alert`
- **Abrir Web Dashboard:** `/Users/ricardoneves/Developer/apps_self_host/b3-acoes-pilot/.venv/bin/b3pilot web`
EOF

chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true
echo "✓ Skill b3-acoes-pilot instalada com sucesso em $DEST_DIR"
