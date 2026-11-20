"""Testes unitários dos conectores multi-provedor de IA (APIs REST e CLIs OAuth)."""

from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from b3pilot.ai.providers import (
    AIConnectorError,
    PROVIDERS,
    complete_with_ai,
    detect_best_provider,
    list_providers_status,
    test_provider_connection,
    validate_base_url,
)
from b3pilot.core.chat import process_chat_query_with_ai
from b3pilot.ledger.db import Base, Position


def test_validate_base_url_security():
    """Garante validação estrita de URLs http/https e bloqueio de esquemas inseguros."""
    assert validate_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"
    assert validate_base_url("http://localhost:11434") == "http://localhost:11434"

    for bad_url in ["", "file:///etc/passwd", "javascript:alert(1)", "ftp://example.com", "https://"]:
        with pytest.raises(AIConnectorError):
            validate_base_url(bad_url)


def test_list_providers_status_no_secrets_leaked(monkeypatch):
    """Garante que status lista todos os provedores sem expor valores das chaves."""
    secret_val = "sk-super-secret-value-123456"
    monkeypatch.setenv("OPENAI_API_KEY", secret_val)
    monkeypatch.setattr("b3pilot.ai.providers._is_ollama_reachable", lambda url: False)

    statuses = list_providers_status()
    ids = {item["id"] for item in statuses}
    assert set(PROVIDERS.keys()).issubset(ids)

    openai_item = next(item for item in statuses if item["id"] == "openai")
    assert openai_item["ready"] is True
    assert secret_val not in str(statuses)


def test_detect_best_provider_priority(monkeypatch):
    """Valida detecção automática priorizando agy > APIs > outras CLIs > deterministic."""
    for env_var in [
        "AI_PROVIDER",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
        "AI_API_KEY",
        "AI_BASE_URL",
    ]:
        monkeypatch.delenv(env_var, raising=False)

    monkeypatch.setattr("b3pilot.ai.providers.find_cli_binary", lambda b: None)
    monkeypatch.setattr("b3pilot.ai.providers._is_ollama_reachable", lambda u: False)

    monkeypatch.setenv("AI_PROVIDER", "auto")
    assert detect_best_provider() == "deterministic"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert detect_best_provider() == "openai"

    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    assert detect_best_provider() == "gemini"

    monkeypatch.setattr("b3pilot.ai.providers.find_cli_binary", lambda b: "/usr/local/bin/agy" if b == "agy" else None)
    assert detect_best_provider() == "agy"

    monkeypatch.setenv("AI_PROVIDER", "groq")
    assert detect_best_provider() == "groq"


@pytest.mark.parametrize(
    "provider_id,binary_name,expected_flags",
    [
        ("agy", "agy", ["--print", "--output-format", "text", "--disable-slash-commands", "--sandbox"]),
        ("gemini_cli", "gemini", ["-p"]),
        ("claude_cli", "claude", ["-p", "--output-format", "text"]),
        ("codex_cli", "codex", ["exec"]),
    ],
)
def test_cli_oauth_connectors_shell_false(monkeypatch, provider_id, binary_name, expected_flags):
    """Valida invocação CLI com shell=False e flags esperadas para cada CLI OAuth."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="Análise sintetizada via CLI", stderr="")

    monkeypatch.setattr(
        "b3pilot.ai.providers.find_cli_binary",
        lambda name: f"/opt/bin/{name}" if name == binary_name else None,
    )
    monkeypatch.setattr("b3pilot.ai.providers.subprocess.run", fake_run)

    res = complete_with_ai(
        provider=provider_id,
        system_prompt="SYS",
        user_prompt="USR",
        model="custom-model",
    )

    assert res["provider"] == provider_id
    assert res["model"] == "custom-model"
    assert res["content"] == "Análise sintetizada via CLI"
    assert captured["kwargs"]["shell"] is False
    assert captured["cmd"][0] == f"/opt/bin/{binary_name}"
    for flag in expected_flags:
        assert flag in captured["cmd"]


def test_gemini_rest_uses_header_not_query_param(monkeypatch):
    """Garante que a API Key do Gemini vai no header x-goog-api-key e nunca na URL."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return SimpleNamespace(
            status_code=200,
            text="{}",
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "Resposta Gemini"}]}}]},
        )

    monkeypatch.setattr("b3pilot.ai.providers.requests.post", fake_post)

    secret = "gemini-secret-xyz"
    res = complete_with_ai(
        provider="gemini",
        system_prompt="SYS",
        user_prompt="USR",
        api_key=secret,
    )

    assert res["provider"] == "gemini"
    assert res["content"] == "Resposta Gemini"
    assert secret not in captured["url"]
    assert "key=" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == secret


@pytest.mark.parametrize(
    "provider_id,expected_host",
    [
        ("openai", "api.openai.com"),
        ("openrouter", "openrouter.ai"),
        ("groq", "api.groq.com"),
        ("deepseek", "api.deepseek.com"),
    ],
)
def test_openai_compatible_rest_providers(monkeypatch, provider_id, expected_host):
    """Valida chamadas REST padrão OpenAI/OpenRouter/Groq/DeepSeek."""
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return SimpleNamespace(
            status_code=200,
            text="{}",
            json=lambda: {"choices": [{"message": {"content": f"OK from {provider_id}"}}]},
        )

    monkeypatch.setattr("b3pilot.ai.providers.requests.post", fake_post)

    res = complete_with_ai(
        provider=provider_id,
        system_prompt="SYS",
        user_prompt="USR",
        api_key="tok-123",
    )

    assert expected_host in captured["url"]
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer tok-123"
    if provider_id == "openrouter":
        assert "HTTP-Referer" in captured["headers"]
        assert "X-Title" in captured["headers"]
    assert res["content"] == f"OK from {provider_id}"


def test_anthropic_and_ollama_rest_connectors(monkeypatch):
    """Valida payloads e headers específicos de Anthropic e Ollama."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers or {}, "json": json})
        if "anthropic.com" in url:
            return SimpleNamespace(
                status_code=200,
                text="{}",
                json=lambda: {"content": [{"type": "text", "text": "OK Claude"}]},
            )
        return SimpleNamespace(
            status_code=200,
            text="{}",
            json=lambda: {"message": {"content": "OK Ollama"}},
        )

    monkeypatch.setattr("b3pilot.ai.providers.requests.post", fake_post)

    res_anth = complete_with_ai(
        provider="anthropic",
        system_prompt="SYS",
        user_prompt="USR",
        api_key="anth-key",
    )
    assert res_anth["content"] == "OK Claude"
    assert calls[0]["headers"]["x-api-key"] == "anth-key"
    assert calls[0]["headers"]["anthropic-version"] == "2023-06-01"

    res_oll = complete_with_ai(
        provider="ollama",
        system_prompt="SYS",
        user_prompt="USR",
    )
    assert res_oll["content"] == "OK Ollama"
    assert calls[1]["url"] == "http://localhost:11434/api/chat"
    assert calls[1]["json"]["stream"] is False


def test_process_chat_query_with_ai_modes_and_fallback(monkeypatch):
    """Valida modo determinístico, modo IA ancorado e fallback gracioso em erro."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.add(
        Position(
            ticker="PETR4",
            quantity=100,
            average_price=36.00,
            total_cost=3600.00,
            stop_loss=33.00,
            take_profit=42.00,
            strategy="TREND",
            is_simulated=False,
        )
    )
    session.commit()

    monkeypatch.setattr(
        "b3pilot.core.chat.analyze_market_regime",
        lambda: {"name": "Alta Saudável", "status": "BULL", "allocation_multiplier": 1.0, "allow_ifr2": True, "allow_momentum": True, "allow_dividends": True, "description": "Tendência positiva."},
    )
    monkeypatch.setattr(
        "b3pilot.core.chat.get_portfolio_summary",
        lambda sess, is_simulated=False: {
            "positions": [{"ticker": "PETR4", "quantity": 100, "average_price": 36.0, "current_price": 38.0, "current_value": 3800.0, "unrealized_pnl": 200.0, "unrealized_pnl_pct": 5.55}],
            "current_market_value": 3800.0,
            "total_unrealized_pnl": 200.0,
            "total_unrealized_pnl_pct": 5.55,
        },
    )

    # 1. Modo determinístico
    det = process_chat_query_with_ai("Como está o ibovespa hoje?", session, provider="deterministic")
    assert det["used_ai"] is False
    assert det["provider"] == "deterministic"
    assert "Diagnóstico do Mercado (IBOVESPA)" in det["response"]

    # 2. Modo IA com contexto determinístico ancorado
    seen_prompt = {}

    def fake_complete(**kwargs):
        seen_prompt["user_prompt"] = kwargs["user_prompt"]
        return {"content": "Resumo executivo com IA sobre PETR4 e IBOV.", "provider": "agy", "model": "agy-oauth"}

    monkeypatch.setattr("b3pilot.core.chat.complete_with_ai", fake_complete)
    ai_out = process_chat_query_with_ai("Como está o ibovespa hoje?", session, provider="agy")
    assert ai_out["used_ai"] is True
    assert ai_out["provider"] == "agy"
    assert "PETR4" in seen_prompt["user_prompt"]
    assert "Diagnóstico do Mercado (IBOVESPA)" in seen_prompt["user_prompt"]

    # 3. Fallback gracioso quando o conector falha
    def failing_complete(**kwargs):
        raise AIConnectorError("Sessão expirada")

    monkeypatch.setattr("b3pilot.core.chat.complete_with_ai", failing_complete)
    fb_out = process_chat_query_with_ai("Como está o ibovespa hoje?", session, provider="agy")
    assert fb_out["used_ai"] is False
    assert "Fallback para motor determinístico local" in fb_out["warning"]
    assert "Diagnóstico do Mercado (IBOVESPA)" in fb_out["response"]

    session.close()


def test_test_provider_connection_deterministic():
    """Garante que test_provider_connection funciona para modo determinístico."""
    res = test_provider_connection("deterministic")
    assert res["ok"] is True
    assert res["provider"] == "deterministic"
