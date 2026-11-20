#!/usr/bin/env bash
# Script para registrar a Skill b3-acoes-pilot no Antigravity CLI (agy) e/ou outras CLIs de IA

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BIN_PATH="${PROJECT_DIR}/.venv/bin/b3pilot"

INSTALL_ALL=false
INSTALL_CLAUDE=false
INSTALL_GEMINI_CLI=false

for arg in "$@"; do
  case "$arg" in
    --all)
      INSTALL_ALL=true
      ;;
    --claude)
      INSTALL_CLAUDE=true
      ;;
    --gemini-cli)
      INSTALL_GEMINI_CLI=true
      ;;
  esac
done

write_skill() {
  local target_dir="$1"
  mkdir -p "$target_dir"
  cat << EOF > "${target_dir}/SKILL.md"
---
name: b3-acoes-pilot
description: |
  Assistente autônomo de Swing Trade, Proventos (Dividendos e JCP na Data COM) e Gestão Fiscal para ações da B3 (Brasil).
  Ative esta skill quando o usuário solicitar:
  - Análise ou situação atual da carteira de ações na B3.
  - Varredura de mercado / scanner concorrente de compras (IFR2 com stop dinâmico, Seguidor de Tendência, Retomada de Fundo / Pivôs).
  - Consulta se deve COMPRAR, VENDER ou AGUARDAR determinada ação antes da abertura ou durante o pregão.
  - Consulta de saídas obrigatórias (Stop Loss, Alvo, Trailing Stop e Time-Stop).
  - Consulta de calendário de dividendos, JCP e próximas Datas COM.
  - Registro de ordens de compra ou venda de ações (reais ou simuladas).
  - Auditoria de travas de baixa e estruturas com opções.
  - Cálculo de imposto de renda, apuração da isenção de R\$ 20.000, compensação de prejuízos e emissão de DARF (Código 6015).
  - Abertura do dashboard visual no navegador.
---

# B3 Ações Pilot (Antigravity agy Native)

Esta skill permite ao agente interagir diretamente com o sistema local de Swing Trade e Proventos em ${PROJECT_DIR}.

## Comandos Operacionais

O executável CLI está em ${BIN_PATH}.

- **Status da Carteira:** \`${BIN_PATH} status\`
- **Scanner de Compras:** \`${BIN_PATH} scan\`
- **Calendário de Proventos:** \`${BIN_PATH} dividends\`
- **Comprar Ação:** \`${BIN_PATH} buy TICKER QUANTIDADE PRECO\`
- **Vender Ação:** \`${BIN_PATH} sell TICKER QUANTIDADE PRECO\`
- **Gestão Fiscal e DARF:** \`${BIN_PATH} taxes\`
- **Rotina Matinal de Alertas:** \`${BIN_PATH} alert\`
- **Abrir Web Dashboard:** \`${BIN_PATH} web\`
- **Consultar Assistente (com IA):** \`${BIN_PATH} ask --ai "PERGUNTA"\`
EOF
  echo "✓ Skill b3-acoes-pilot instalada com sucesso em ${target_dir}"
}

# Padrão: Antigravity CLI (agy)
write_skill "$HOME/.gemini/config/skills/b3-acoes-pilot"

if [ "$INSTALL_ALL" = true ] || [ "$INSTALL_CLAUDE" = true ]; then
  write_skill "$HOME/.claude/skills/b3-acoes-pilot"
fi

if [ "$INSTALL_ALL" = true ] || [ "$INSTALL_GEMINI_CLI" = true ]; then
  write_skill "$HOME/.gemini/skills/b3-acoes-pilot"
fi

chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true
