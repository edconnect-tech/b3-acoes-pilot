# Política de Segurança (`SECURITY.md`) 🔒

## Relato de Vulnerabilidades
Se você identificar qualquer falha de segurança, vazamento potencial de credenciais ou bug crítico de cálculo tributário/risco, **não abra uma Issue pública** inicialmente.

Envie um relato detalhado para: **ricardo@edconnect.com.br**

Inclua:
- Descrição técnica do problema e impacto estimado.
- Passos para reproduzir em ambiente local isolado.

## Boas Práticas Obrigatórias para Usuários
- **Nunca versione seu arquivo `.env`**, `portfolio.db`, backups (`.bak`) ou planilhas pessoais (`.xlsx`, `.csv`).
- Mantenha o `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e chaves de API de IA (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.) exclusivamente no `.env` local ou na sessão do navegador.
- Ao utilizar conectores OAuth nativos (`agy`, `gemini`, `claude`, `codex`), faça o login diretamente na CLI oficial no seu terminal — o B3 Ações Pilot nunca lê nem armazena suas senhas Google/OpenAI/Anthropic.
