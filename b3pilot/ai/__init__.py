"""Conectores multi-provedor de IA (APIs REST e CLIs com login OAuth, incluindo Google agy)."""

from b3pilot.ai.providers import (
    AIConnectorError,
    PROVIDERS,
    complete_with_ai,
    detect_best_provider,
    find_cli_binary,
    list_providers_status,
    test_provider_connection,
    validate_base_url,
)

__all__ = [
    "AIConnectorError",
    "PROVIDERS",
    "complete_with_ai",
    "detect_best_provider",
    "find_cli_binary",
    "list_providers_status",
    "test_provider_connection",
    "validate_base_url",
]
