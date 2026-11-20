# Contribuindo com o B3 Ações Pilot 🤝

Agradecemos o interesse em evoluir o **B3 Ações Pilot**!

## Licença e Termos de Contribuição
Este projeto é distribuído sob a **Business Source License 1.1 (BSL 1.1)** com licenciamento pela **EdConnect Tecnologia Ltda** (`Change Date: 2030-11-20` -> `GPL-3.0-or-later`). Ao abrir um Pull Request, você concorda que sua contribuição será distribuída sob os mesmos termos da licença do repositório.

## Princípios Arquiteturais Obrigatórios
1. **Determinismo Numérico (Zero Trust no LLM):** Indicadores técnicos, position sizing, gestão de risco e apuração fiscal/DARF devem sempre ser calculados em Python determinístico, nunca delegados a modelos de linguagem.
2. **Privacidade e Zero Trust:** Nunca inclua tokens, chaves de API, planilhas pessoais ou bancos `.db` nos commits. Use `shell=False` em chamadas de sistema e valide URLs externas.
3. **Estética Clean / Modo Claro:** A interface web em Streamlit prioriza contraste acessível (WCAG 2.2 AA) em modo claro e fontes de sistema.

## Fluxo de Desenvolvimento Local
```bash
git clone https://github.com/edconnect-tech/b3-acoes-pilot.git
cd b3-acoes-pilot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -v
```

Antes de enviar um Pull Request:
- Garanta que toda a suíte `pytest -v` passe sem erros.
- Escreva testes unitários para novas regras de negócio, estratégias ou conectores.
- Mantenha commits pequenos, claros e descritivos.
