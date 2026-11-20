"""Conectores multi-provedor de IA com arquitetura Zero Trust no LLM.

Suporta:
1. Modo Determinístico local (sem LLM).
2. CLIs com login OAuth nativo (Google Antigravity `agy`, Gemini CLI, Claude Code CLI, OpenAI Codex CLI).
3. APIs REST consolidadas (Google Gemini, OpenAI, Anthropic, OpenRouter, Groq, DeepSeek, Ollama e OpenAI-Compatible).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

# Ordem de prioridade quando AI_PROVIDER=auto
AUTO_PRIORITY_ORDER: List[str] = [
    "agy",
    "gemini",
    "openai",
    "anthropic",
    "openrouter",
    "groq",
    "deepseek",
    "gemini_cli",
    "claude_cli",
    "codex_cli",
    "deterministic",
]


class AIConnectorError(RuntimeError):
    """Erro sanitizado de comunicação ou configuração de conector de IA."""


PROVIDERS: Dict[str, Dict[str, Any]] = {
    "deterministic": {
        "name": "Local Determinístico (Python 64-bit, sem LLM)",
        "auth_type": "none",
        "default_model": "python-64bit",
        "login_hint": "Motor nativo sem necessidade de login ou API Key.",
    },
    "agy": {
        "name": "Google Antigravity CLI (agy — Login Google)",
        "auth_type": "cli_oauth",
        "binary": "agy",
        "default_model": None,
        "login_hint": "Execute 'agy' no terminal para fazer login com sua conta Google.",
    },
    "gemini_cli": {
        "name": "Google Gemini CLI (Login Google)",
        "auth_type": "cli_oauth",
        "binary": "gemini",
        "default_model": None,
        "login_hint": "Execute 'gemini' no terminal para autenticar com sua conta Google.",
    },
    "claude_cli": {
        "name": "Claude Code CLI (Login Anthropic)",
        "auth_type": "cli_oauth",
        "binary": "claude",
        "default_model": None,
        "login_hint": "Execute 'claude login' no terminal.",
    },
    "codex_cli": {
        "name": "OpenAI Codex CLI (Login OpenAI/ChatGPT)",
        "auth_type": "cli_oauth",
        "binary": "codex",
        "default_model": None,
        "login_hint": "Execute 'codex login' no terminal.",
    },
    "gemini": {
        "name": "Google Gemini API (AI Studio)",
        "auth_type": "api_key",
        "env_key": "GEMINI_API_KEY",
        "fallback_env_keys": ["GOOGLE_API_KEY"],
        "default_model": "gemini-2.5-flash",
        "default_base": "https://generativelanguage.googleapis.com/v1beta",
        "login_hint": "Defina GEMINI_API_KEY no .env ou informe na sessão.",
    },
    "openai": {
        "name": "OpenAI API (GPT / ChatGPT)",
        "auth_type": "api_key",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "default_base": "https://api.openai.com/v1",
        "login_hint": "Defina OPENAI_API_KEY no .env ou informe na sessão.",
    },
    "anthropic": {
        "name": "Anthropic Claude API",
        "auth_type": "api_key",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
        "default_base": "https://api.anthropic.com/v1",
        "login_hint": "Defina ANTHROPIC_API_KEY no .env ou informe na sessão.",
    },
    "openrouter": {
        "name": "OpenRouter (200+ modelos)",
        "auth_type": "api_key",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "google/gemini-2.5-flash",
        "default_base": "https://openrouter.ai/api/v1",
        "login_hint": "Defina OPENROUTER_API_KEY no .env ou informe na sessão.",
    },
    "groq": {
        "name": "Groq Cloud",
        "auth_type": "api_key",
        "env_key": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "default_base": "https://api.groq.com/openai/v1",
        "login_hint": "Defina GROQ_API_KEY no .env ou informe na sessão.",
    },
    "deepseek": {
        "name": "DeepSeek API",
        "auth_type": "api_key",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "default_base": "https://api.deepseek.com/v1",
        "login_hint": "Defina DEEPSEEK_API_KEY no .env ou informe na sessão.",
    },
    "ollama": {
        "name": "Ollama Local (100% Privado)",
        "auth_type": "local",
        "env_base": "OLLAMA_BASE_URL",
        "default_model": "llama3.2",
        "default_base": "http://localhost:11434",
        "login_hint": "Inicie o Ollama localmente (ollama serve) na porta 11434.",
    },
    "openai_compatible": {
        "name": "Endpoint OpenAI-Compatible (LM Studio, vLLM, Azure, etc.)",
        "auth_type": "api_key",
        "env_key": "AI_API_KEY",
        "env_base": "AI_BASE_URL",
        "default_model": "gpt-4o-mini",
        "default_base": "",
        "login_hint": "Informe AI_BASE_URL (e AI_API_KEY se o servidor exigir).",
    },
}


def find_cli_binary(binary_name: str) -> Optional[str]:
    """Localiza um binário CLI no PATH ou em diretórios padrão de usuário/macOS/Linux."""
    if not binary_name or "/" in binary_name or "\\" in binary_name:
        return None

    which_hit = shutil.which(binary_name)
    if which_hit:
        return which_hit

    candidate_dirs = [
        Path.home() / ".local" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path.home() / ".npm-global" / "bin",
    ]
    for directory in candidate_dirs:
        candidate = directory / binary_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def validate_base_url(url: str) -> str:
    """Valida e normaliza URL base HTTP/HTTPS para evitar esquemas inseguros ou hosts vazios."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise AIConnectorError("URL base não informada para o conector de IA.")

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise AIConnectorError(
            f"Esquema de URL inválido ({parsed.scheme or 'vazio'}). Apenas http:// ou https:// são permitidos."
        )
    if not parsed.netloc:
        raise AIConnectorError("URL base inválida: host ausente.")

    return cleaned.rstrip("/")


def _sanitize_error_text(text: str, secret: Optional[str] = None) -> str:
    """Remove possíveis segredos de mensagens de erro antes de retornar ao usuário."""
    clean = (text or "").strip()
    if secret and secret in clean:
        clean = clean.replace(secret, "***")
    return clean[:500]


def _resolve_api_key(provider_id: str, explicit_key: Optional[str] = None) -> str:
    """Obtém a API Key sem nunca persistir ou expor o segredo."""
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    meta = PROVIDERS[provider_id]
    env_key = meta.get("env_key")
    if env_key:
        val = os.getenv(env_key, "").strip()
        if val:
            return val

    for fb_key in meta.get("fallback_env_keys", []):
        val = os.getenv(fb_key, "").strip()
        if val:
            return val

    # Fallback genérico caso o usuário tenha configurado apenas AI_API_KEY para o provedor ativo
    configured_provider = os.getenv("AI_PROVIDER", "").strip().lower()
    if configured_provider == provider_id:
        generic_key = os.getenv("AI_API_KEY", "").strip()
        if generic_key:
            return generic_key

    return ""


def _resolve_base_url(provider_id: str, explicit_base: Optional[str] = None) -> str:
    """Obtém e valida a URL base de APIs REST."""
    meta = PROVIDERS[provider_id]
    candidate = (explicit_base or "").strip()

    if not candidate and meta.get("env_base"):
        candidate = os.getenv(meta["env_base"], "").strip()

    if not candidate and os.getenv("AI_PROVIDER", "").strip().lower() == provider_id:
        candidate = os.getenv("AI_BASE_URL", "").strip()

    if not candidate:
        candidate = meta.get("default_base", "")

    return validate_base_url(candidate)


def _is_ollama_reachable(base_url: str) -> bool:
    """Verifica rapidamente se um servidor Ollama local responde."""
    try:
        validated = validate_base_url(base_url)
        resp = requests.get(f"{validated}/api/tags", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def list_providers_status() -> List[Dict[str, Any]]:
    """Retorna o estado de disponibilidade de todos os conectores sem expor segredos."""
    statuses: List[Dict[str, Any]] = []
    for pid, meta in PROVIDERS.items():
        auth_type = meta["auth_type"]
        ready = False
        binary_path: Optional[str] = None
        base_url: Optional[str] = None
        status_label = "⚠️ Configurar"

        if auth_type == "none":
            ready = True
            status_label = "✓ Sempre disponível"
        elif auth_type == "cli_oauth":
            binary_path = find_cli_binary(meta["binary"])
            ready = bool(binary_path)
            status_label = "✓ CLI detectada" if ready else "⚠️ CLI não encontrada"
        elif auth_type == "api_key":
            has_key = bool(_resolve_api_key(pid))
            if pid == "openai_compatible":
                raw_base = os.getenv("AI_BASE_URL", "").strip()
                if raw_base:
                    try:
                        base_url = validate_base_url(raw_base)
                        ready = True
                        status_label = "✓ Endpoint configurado"
                    except AIConnectorError:
                        ready = False
                        status_label = "⚠️ URL inválida"
                else:
                    status_label = "⚠️ Informar AI_BASE_URL"
            else:
                base_url = meta.get("default_base")
                ready = has_key
                status_label = "✓ API Key ativa" if ready else f"⚠️ Definir {meta.get('env_key')}"
        elif auth_type == "local":
            raw_base = os.getenv(meta.get("env_base", "OLLAMA_BASE_URL"), meta["default_base"])
            try:
                base_url = validate_base_url(raw_base)
            except AIConnectorError:
                base_url = meta["default_base"]
            ready = _is_ollama_reachable(base_url)
            status_label = "✓ Ollama ativo" if ready else "⚠️ Ollama offline"

        statuses.append(
            {
                "id": pid,
                "name": meta["name"],
                "auth_type": auth_type,
                "ready": ready,
                "default_model": meta.get("default_model"),
                "env_key": meta.get("env_key"),
                "binary_path": binary_path,
                "base_url": base_url,
                "login_hint": meta["login_hint"],
                "status_label": status_label,
            }
        )
    return statuses


def detect_best_provider() -> str:
    """Detecta o provedor configurado via AI_PROVIDER ou seleciona o melhor disponível em modo 'auto'."""
    configured = os.getenv("AI_PROVIDER", "deterministic").strip().lower()
    if configured and configured != "auto":
        if configured in PROVIDERS:
            return configured
        return "deterministic"

    status_map = {item["id"]: item for item in list_providers_status()}
    for pid in AUTO_PRIORITY_ORDER:
        item = status_map.get(pid)
        if item and item["ready"]:
            return pid
    return "deterministic"


def _run_cli_provider(
    provider_id: str,
    system_prompt: str,
    user_prompt: str,
    model: Optional[str],
    timeout: int,
) -> Dict[str, Any]:
    """Executa provedores CLI com login OAuth nativo usando subprocess seguro (shell=False)."""
    meta = PROVIDERS[provider_id]
    binary_name = meta["binary"]
    bin_path = find_cli_binary(binary_name)
    if not bin_path:
        raise AIConnectorError(
            f"Binário '{binary_name}' não encontrado no sistema. {meta['login_hint']}"
        )

    combined_prompt = (
        f"[INSTRUÇÕES DE SISTEMA]\n{system_prompt.strip()}\n\n"
        f"[SOLICITAÇÃO E DADOS DETERMINÍSTICOS]\n{user_prompt.strip()}"
    )

    chosen_model = (model or "").strip() or None

    if provider_id == "agy":
        cmd = [
            bin_path,
            "--print",
            combined_prompt,
            "--output-format",
            "text",
            "--disable-slash-commands",
            "--sandbox",
            "--print-timeout",
            f"{int(timeout)}s",
        ]
        if chosen_model:
            cmd.extend(["--model", chosen_model])
    elif provider_id == "gemini_cli":
        cmd = [bin_path, "-p", combined_prompt]
        if chosen_model:
            cmd.extend(["-m", chosen_model])
    elif provider_id == "claude_cli":
        cmd = [bin_path, "-p", combined_prompt, "--output-format", "text"]
        if chosen_model:
            cmd.extend(["--model", chosen_model])
    elif provider_id == "codex_cli":
        cmd = [bin_path, "exec", combined_prompt]
        if chosen_model:
            cmd.extend(["-m", chosen_model])
    else:
        raise AIConnectorError(f"Conector CLI não suportado: {provider_id}")

    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AIConnectorError(
            f"Tempo limite ({timeout}s) excedido ao consultar '{binary_name}'."
        ) from exc
    except OSError as exc:
        raise AIConnectorError(f"Falha ao executar '{binary_name}': {exc}") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        detail = _sanitize_error_text(stderr or stdout)
        auth_words = ("login", "auth", "credential", "token", "unauthorized", "sign in")
        if any(w in detail.lower() for w in auth_words):
            raise AIConnectorError(
                f"Autenticação necessária no '{binary_name}'. {meta['login_hint']} ({detail})"
            )
        raise AIConnectorError(
            f"Conector '{binary_name}' retornou código {proc.returncode}: {detail or 'erro desconhecido'}."
        )

    if not stdout:
        raise AIConnectorError(
            f"Conector '{binary_name}' retornou resposta vazia. Verifique se está logado ({meta['login_hint']})."
        )

    return {
        "content": stdout,
        "provider": provider_id,
        "model": chosen_model or f"{binary_name}-oauth",
    }


def _call_gemini_rest(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    """Chama a API REST oficial do Google Gemini enviando a chave no header x-goog-api-key."""
    url = f"{base_url}/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AIConnectorError(
            f"Erro de rede na API Gemini: {_sanitize_error_text(str(exc), api_key)}"
        ) from exc

    if resp.status_code >= 400:
        raise AIConnectorError(
            f"API Gemini retornou HTTP {resp.status_code}: {_sanitize_error_text(resp.text, api_key)}"
        )

    try:
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIConnectorError("Resposta inesperada da API Gemini.") from exc

    if not text:
        raise AIConnectorError("API Gemini retornou conteúdo vazio.")

    return {"content": text, "provider": "gemini", "model": model}


def _call_anthropic_rest(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    """Chama a API REST Messages da Anthropic."""
    url = f"{base_url}/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 1500,
        "temperature": 0.2,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AIConnectorError(
            f"Erro de rede na API Anthropic: {_sanitize_error_text(str(exc), api_key)}"
        ) from exc

    if resp.status_code >= 400:
        raise AIConnectorError(
            f"API Anthropic retornou HTTP {resp.status_code}: {_sanitize_error_text(resp.text, api_key)}"
        )

    try:
        data = resp.json()
        blocks = data["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    except (ValueError, KeyError, TypeError) as exc:
        raise AIConnectorError("Resposta inesperada da API Anthropic.") from exc

    if not text:
        raise AIConnectorError("API Anthropic retornou conteúdo vazio.")

    return {"content": text, "provider": "anthropic", "model": model}


def _call_openai_compatible_rest(
    provider_id: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    """Chama OpenAI, OpenRouter, Groq, DeepSeek ou qualquer endpoint OpenAI-Compatible."""
    url = f"{base_url}/chat/completions"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if provider_id == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/edconnect-tech/b3-acoes-pilot"
        headers["X-Title"] = "B3 Acoes Pilot"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AIConnectorError(
            f"Erro de rede em {provider_id}: {_sanitize_error_text(str(exc), api_key)}"
        ) from exc

    if resp.status_code >= 400:
        raise AIConnectorError(
            f"Provedor {provider_id} retornou HTTP {resp.status_code}: {_sanitize_error_text(resp.text, api_key)}"
        )

    try:
        data = resp.json()
        text = str(data["choices"][0]["message"]["content"]).strip()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIConnectorError(f"Resposta inesperada do provedor {provider_id}.") from exc

    if not text:
        raise AIConnectorError(f"Provedor {provider_id} retornou conteúdo vazio.")

    return {"content": text, "provider": provider_id, "model": model}


def _call_ollama_rest(
    system_prompt: str,
    user_prompt: str,
    model: str,
    base_url: str,
    timeout: int,
) -> Dict[str, Any]:
    """Chama a API local do Ollama."""
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise AIConnectorError(
            f"Erro ao conectar ao Ollama em {base_url}: {_sanitize_error_text(str(exc))}"
        ) from exc

    if resp.status_code >= 400:
        raise AIConnectorError(
            f"Ollama retornou HTTP {resp.status_code}: {_sanitize_error_text(resp.text)}"
        )

    try:
        data = resp.json()
        text = str(data["message"]["content"]).strip()
    except (ValueError, KeyError, TypeError) as exc:
        raise AIConnectorError("Resposta inesperada do Ollama.") from exc

    if not text:
        raise AIConnectorError("Ollama retornou conteúdo vazio.")

    return {"content": text, "provider": "ollama", "model": model}


def complete_with_ai(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Executa uma inferência em qualquer provedor cadastrado (CLI OAuth ou REST API)."""
    pid = (provider or "deterministic").strip().lower()
    if pid == "auto":
        pid = detect_best_provider()

    if pid not in PROVIDERS:
        raise AIConnectorError(f"Provedor de IA desconhecido: '{pid}'.")

    if pid == "deterministic":
        raise AIConnectorError("Modo determinístico não utiliza conector LLM externo.")

    meta = PROVIDERS[pid]
    effective_timeout = int(timeout or os.getenv("AI_TIMEOUT_SECONDS", "60"))

    explicit_or_env_model = (model or "").strip()
    if not explicit_or_env_model and os.getenv("AI_PROVIDER", "").strip().lower() == pid:
        explicit_or_env_model = os.getenv("AI_MODEL", "").strip()

    if meta["auth_type"] == "cli_oauth":
        return _run_cli_provider(
            provider_id=pid,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=explicit_or_env_model or meta.get("default_model"),
            timeout=effective_timeout,
        )

    chosen_model = explicit_or_env_model or meta.get("default_model") or ""
    if not chosen_model:
        raise AIConnectorError(f"Modelo não informado para o provedor '{pid}'.")

    resolved_base = _resolve_base_url(pid, explicit_base=base_url)

    if pid == "ollama":
        return _call_ollama_rest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=chosen_model,
            base_url=resolved_base,
            timeout=effective_timeout,
        )

    resolved_key = _resolve_api_key(pid, explicit_key=api_key)
    if pid != "openai_compatible" and not resolved_key:
        raise AIConnectorError(
            f"Chave de API ausente para '{pid}'. {meta['login_hint']}"
        )

    if pid == "gemini":
        return _call_gemini_rest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=chosen_model,
            api_key=resolved_key,
            base_url=resolved_base,
            timeout=effective_timeout,
        )

    if pid == "anthropic":
        return _call_anthropic_rest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=chosen_model,
            api_key=resolved_key,
            base_url=resolved_base,
            timeout=effective_timeout,
        )

    return _call_openai_compatible_rest(
        provider_id=pid,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=chosen_model,
        api_key=resolved_key,
        base_url=resolved_base,
        timeout=effective_timeout,
    )


def test_provider_connection(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Valida a conectividade e autenticação do provedor escolhido com um prompt mínimo."""
    pid = (provider or "auto").strip().lower()
    if pid == "auto":
        pid = detect_best_provider()

    if pid == "deterministic":
        return {
            "ok": True,
            "provider": "deterministic",
            "model": "python-64bit",
            "message": "Motor determinístico local ativo (sem dependência externa).",
        }

    try:
        res = complete_with_ai(
            provider=pid,
            system_prompt="Responda apenas com: OK.",
            user_prompt="Teste de conexão.",
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=30,
        )
        return {
            "ok": True,
            "provider": res["provider"],
            "model": res["model"],
            "message": f"Conectado com sucesso ({res['content'][:60]}).",
        }
    except AIConnectorError as exc:
        return {
            "ok": False,
            "provider": pid,
            "model": model or PROVIDERS.get(pid, {}).get("default_model") or "-",
            "message": str(exc),
        }


test_provider_connection.__test__ = False  # Evita coleta acidental pelo pytest quando importada em testes
