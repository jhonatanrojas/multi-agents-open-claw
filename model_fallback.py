"""
model_fallback.py - Sistema de Fallbacks Automáticos para Modelos

Implementa rotación automática de modelos cuando hay errores de API
(rate limits, saldo insuficiente, etc.)

Uso:
    from model_fallback import ModelFallbackManager, execute_with_fallback

    manager = ModelFallbackManager()
    result = await execute_with_fallback("byte", prompt, manager)
"""

from __future__ import annotations

import json
import os
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable
from enum import Enum

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MODELS_CONFIG_PATH = BASE_DIR / "models_config.json"

# Cache configuration with environment variable support
MODEL_STATUS_CACHE_PATH = Path(
    os.getenv("MODEL_STATUS_CACHE_PATH", "/var/cache/openclaw/model_status.json")
)
CACHE_TTL_SECONDS = int(os.getenv("MODEL_STATUS_CACHE_TTL", "300"))  # 5 minutes default

# Códigos de error que disparan fallback
FALLBACK_ERROR_CODES = {429, 402, 503, 502, 504}
FALLBACK_ERROR_SUBSTRINGS = [
    "rate limit",
    "insufficient balance",
    "quota exceeded",
    "temporarily unavailable",
    "service unavailable",
    "too many requests",
    "api key",
    "unauthorized",
    "forbidden",
]


class ErrorCategory(Enum):
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    SERVICE_ERROR = "service_error"
    AUTH_ERROR = "auth_error"
    UNKNOWN = "unknown"


@dataclass
class ModelStatus:
    """Estado de un modelo específico."""

    qualified_name: str
    last_error: str | None = None
    last_error_code: int | None = None
    last_error_time: float = 0.0
    consecutive_failures: int = 0
    is_available: bool = True
    cooldown_until: float = 0.0


@dataclass
class FallbackConfig:
    """Configuración de fallbacks por agente."""

    primary: str
    fallbacks: list[str] = field(default_factory=list)
    current_index: int = 0
    cooldown_seconds: int = 300  # 5 minutos de cooldown tras fallo
    max_consecutive_failures: int = 3


# Configuración por defecto de fallbacks por agente
DEFAULT_FALLBACK_CHAINS = {
    "arch": [
        "nvidia/z-ai/glm5",
        "deepseek/deepseek-chat",
        "mistral/mistral-large-latest",
        "nvidia/moonshotai/kimi-k2.5",
    ],
    "byte": [
        "nvidia/moonshotai/kimi-k2.5",
        "deepseek/deepseek-chat",
        "mistral/mistral-large-latest",
        "nvidia/z-ai/glm5",
    ],
    "pixel": [
        "deepseek/deepseek-chat",
        "mistral/mistral-large-latest",
        "nvidia/z-ai/glm5",
        "nvidia/moonshotai/kimi-k2.5",
    ],
    "main": [
        "nvidia/z-ai/glm5",
        "deepseek/deepseek-chat",
        "mistral/mistral-large-latest",
    ],
}


class CircuitBreaker:
    """
    Circuit Breaker para evitar intentar modelos que han fallado recientemente.

    Estados:
    - CLOSED: Funcionando normalmente
    - OPEN: No intentar, esperar cooldown
    - HALF_OPEN: Intentar una vez para ver si recuperó
    """

    def __init__(self, cooldown_seconds: int = 300, max_failures: int = 3):
        self.cooldown_seconds = cooldown_seconds
        self.max_failures = max_failures
        self._failures: dict[str, list[float]] = {}

    def record_failure(self, model: str) -> None:
        """Registrar un fallo para el modelo."""
        now = time.time()
        if model not in self._failures:
            self._failures[model] = []
        self._failures[model].append(now)
        # Limpiar fallos antiguos
        cutoff = now - self.cooldown_seconds
        self._failures[model] = [t for t in self._failures[model] if t > cutoff]

    def record_success(self, model: str) -> None:
        """Registrar éxito, resetear contador."""
        if model in self._failures:
            self._failures[model] = []

    def is_available(self, model: str) -> bool:
        """Verificar si el modelo está disponible para uso."""
        if model not in self._failures:
            return True
        # Contar fallos recientes
        now = time.time()
        cutoff = now - self.cooldown_seconds
        recent_failures = [t for t in self._failures[model] if t > cutoff]
        return len(recent_failures) < self.max_failures

    def get_remaining_cooldown(self, model: str) -> float:
        """Obtener segundos restantes de cooldown."""
        if model not in self._failures or not self._failures[model]:
            return 0.0
        last_failure = max(self._failures[model])
        elapsed = time.time() - last_failure
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)


class ModelFallbackManager:
    """
    Gestor de fallbacks de modelos con Circuit Breaker.

    Mantiene estado de salud de cada modelo y rota automáticamente
    cuando hay errores.
    """

    def __init__(
        self,
        fallback_chains: dict[str, list[str]] | None = None,
        cooldown_seconds: int = 300,
    ):
        self.fallback_chains = fallback_chains or DEFAULT_FALLBACK_CHAINS
        self.circuit_breaker = CircuitBreaker(cooldown_seconds=cooldown_seconds)
        self._model_status: dict[str, ModelStatus] = {}
        self._current_model_index: dict[str, int] = {}

    def get_fallback_chain(self, agent_id: str) -> list[str]:
        """Obtener cadena de fallbacks para un agente."""
        return self.fallback_chains.get(agent_id, self.fallback_chains.get("main", []))

    def get_next_available_model(self, agent_id: str) -> str | None:
        """
        Obtener el siguiente modelo disponible en la cadena de fallbacks.

        Returns:
            Nombre calificado del modelo, o None si todos están en cooldown.
        """
        chain = self.get_fallback_chain(agent_id)
        for model in chain:
            if self.circuit_breaker.is_available(model):
                return model
        # Si todos están en cooldown, usar el primero (forzar intento)
        return chain[0] if chain else None

    def record_success(self, agent_id: str, model: str) -> None:
        """Registrar ejecución exitosa."""
        self.circuit_breaker.record_success(model)
        if model not in self._model_status:
            self._model_status[model] = ModelStatus(qualified_name=model)
        self._model_status[model].is_available = True
        self._model_status[model].consecutive_failures = 0
        log.info(f"[fallback] Model {model} OK for agent {agent_id}")

    def record_failure(
        self, agent_id: str, model: str, error: str, error_code: int | None = None
    ) -> str | None:
        """
        Registrar fallo y obtener siguiente modelo disponible.

        Args:
            agent_id: ID del agente
            model: Modelo que falló
            error: Mensaje de error
            error_code: Código de error HTTP (opcional)

        Returns:
            Siguiente modelo disponible, o None si no hay alternativas.
        """
        self.circuit_breaker.record_failure(model)

        if model not in self._model_status:
            self._model_status[model] = ModelStatus(qualified_name=model)

        self._model_status[model].last_error = error
        self._model_status[model].last_error_code = error_code
        self._model_status[model].last_error_time = time.time()
        self._model_status[model].consecutive_failures += 1
        self._model_status[model].is_available = False

        log.warning(
            f"[fallback] Model {model} FAILED for agent {agent_id}: {error[:100]}"
        )

        # Obtener siguiente disponible
        return self.get_next_available_model(agent_id)

    def get_status_report(self) -> dict[str, Any]:
        """Generar reporte de estado de todos los modelos."""
        report = {
            "models": {},
            "circuit_breaker": {
                "failures": {
                    k: len(v) for k, v in self.circuit_breaker._failures.items()
                },
                "cooldown_seconds": self.circuit_breaker.cooldown_seconds,
            },
        }

        for agent_id, chain in self.fallback_chains.items():
            report["models"][agent_id] = {
                "chain": chain,
                "current": self.get_next_available_model(agent_id),
                "available": [
                    m for m in chain if self.circuit_breaker.is_available(m)
                ],
                "cooldown": {
                    m: self.circuit_breaker.get_remaining_cooldown(m)
                    for m in chain
                    if not self.circuit_breaker.is_available(m)
                },
            }

        return report

    def categorize_error(self, error: str, error_code: int | None) -> ErrorCategory:
        """Categorizar el tipo de error."""
        error_lower = error.lower()

        if error_code == 429 or "rate limit" in error_lower:
            return ErrorCategory.RATE_LIMIT
        if error_code == 402 or "balance" in error_lower or "quota" in error_lower:
            return ErrorCategory.INSUFFICIENT_BALANCE
        if error_code in {503, 502, 504}:
            return ErrorCategory.SERVICE_ERROR
        if error_code in {401, 403} or "unauthorized" in error_lower:
            return ErrorCategory.AUTH_ERROR
        return ErrorCategory.UNKNOWN


# Instancia global
_fallback_manager: ModelFallbackManager | None = None


def get_fallback_manager() -> ModelFallbackManager:
    """Obtener instancia singleton del gestor de fallbacks."""
    global _fallback_manager
    if _fallback_manager is None:
        # Intentar cargar configuración personalizada
        config_path = BASE_DIR / "models_fallback_config.json"
        custom_chains = None
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    custom_chains = config.get("fallback_chains")
            except Exception as e:
                log.warning(f"Could not load fallback config: {e}")

        _fallback_manager = ModelFallbackManager(fallback_chains=custom_chains)
    return _fallback_manager


def should_trigger_fallback(error: str, error_code: int | None = None) -> bool:
    """Determinar si un error debería disparar fallback."""
    if error_code and error_code in FALLBACK_ERROR_CODES:
        return True
    error_lower = error.lower()
    return any(sub in error_lower for sub in FALLBACK_ERROR_SUBSTRINGS)


# Funciones de conveniencia para usar desde orchestrator.py
def get_model_for_agent(agent_id: str) -> str | None:
    """Obtener el mejor modelo disponible para un agente."""
    manager = get_fallback_manager()
    return manager.get_next_available_model(agent_id)


def report_model_success(agent_id: str, model: str) -> None:
    """Reportar éxito de modelo."""
    manager = get_fallback_manager()
    manager.record_success(agent_id, model)


def report_model_failure(
    agent_id: str, model: str, error: str, error_code: int | None = None
) -> str | None:
    """Reportar fallo y obtener siguiente modelo."""
    manager = get_fallback_manager()
    return manager.record_failure(agent_id, model, error, error_code)


def get_models_health_report() -> dict[str, Any]:
    """Obtener reporte de salud de modelos."""
    manager = get_fallback_manager()
    return manager.get_status_report()


# ── Persistencia de estado (Tarea 3.3) ────────────────────────────────────────

def save_model_status_cache() -> None:
    """
    Guardar estado de modelos a disco.
    
    Persiste el estado del circuit breaker para sobrevivir reinicios.
    Incluye manejo de excepciones y logging explícito.
    """
    manager = get_fallback_manager()
    
    # Filter out entries older than TTL (5 minutes)
    now = time.time()
    cutoff = now - CACHE_TTL_SECONDS
    
    cache_data = {
        "timestamp": now,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "circuit_breaker": {
            model: {
                "failures": [f for f in failures if f > cutoff],
                "last_failure": max((f for f in failures if f > cutoff), default=None),
            }
            for model, failures in manager.circuit_breaker._failures.items()
            if failures and any(f > cutoff for f in failures)
        },
        "model_status": {
            model: {
                "last_error": status.last_error,
                "last_error_code": status.last_error_code,
                "last_error_time": status.last_error_time,
                "consecutive_failures": status.consecutive_failures,
                "is_available": status.is_available,
            }
            for model, status in manager._model_status.items()
            if status.last_error_time > cutoff  # Only include recent statuses
        },
    }
    
    try:
        # Ensure cache directory exists
        MODEL_STATUS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Validate directory is writable
        if not os.access(MODEL_STATUS_CACHE_PATH.parent, os.W_OK):
            log.error(f"Cache directory not writable: {MODEL_STATUS_CACHE_PATH.parent}")
            return
        
        with open(MODEL_STATUS_CACHE_PATH, "w") as f:
            json.dump(cache_data, f, indent=2)
        
        log.info(f"Model status cache saved to {MODEL_STATUS_CACHE_PATH}")
        
    except PermissionError as e:
        log.error(f"Permission denied saving model status cache: {e}")
    except OSError as e:
        log.error(f"OS error saving model status cache: {e}")
    except json.JSONEncodeError as e:
        log.error(f"JSON encoding error saving model status cache: {e}")
    except Exception as e:
        log.error(f"Unexpected error saving model status cache: {type(e).__name__}: {e}")


def load_model_status_cache() -> None:
    """
    Cargar estado de modelos desde disco.
    
    Restaura el estado del circuit breaker desde la sesión anterior.
    Valida TTL (no usa entradas de más de 5 minutos).
    Incluye manejo de excepciones con logging explícito.
    """
    if not MODEL_STATUS_CACHE_PATH.exists():
        log.debug(f"Cache file does not exist: {MODEL_STATUS_CACHE_PATH}")
        return
    
    # Validate file is readable
    if not os.access(MODEL_STATUS_CACHE_PATH, os.R_OK):
        log.error(f"Cache file not readable: {MODEL_STATUS_CACHE_PATH}")
        return
    
    try:
        with open(MODEL_STATUS_CACHE_PATH, "r") as f:
            cache_data = json.load(f)
        
        # Validate cache timestamp (ignore if older than TTL)
        cache_timestamp = cache_data.get("timestamp", 0)
        cache_age = time.time() - cache_timestamp
        if cache_age > CACHE_TTL_SECONDS:
            log.info(f"Cache is {cache_age:.0f}s old (TTL: {CACHE_TTL_SECONDS}s), ignoring stale entries")
            return
        
        manager = get_fallback_manager()
        now = time.time()
        cutoff = now - CACHE_TTL_SECONDS
        restored_count = 0
        
        # Restaurar circuit breaker (only entries within TTL)
        for model, data in cache_data.get("circuit_breaker", {}).items():
            last_failure = data.get("last_failure")
            if last_failure and last_failure > cutoff:
                age = now - last_failure
                if age < manager.circuit_breaker.cooldown_seconds:
                    manager.circuit_breaker._failures[model] = [last_failure]
                    restored_count += 1
        
        # Restaurar model_status (only entries within TTL)
        for model, data in cache_data.get("model_status", {}).items():
            last_error_time = data.get("last_error_time", 0)
            if last_error_time > cutoff:
                manager._model_status[model] = ModelStatus(
                    qualified_name=model,
                    last_error=data.get("last_error"),
                    last_error_code=data.get("last_error_code"),
                    last_error_time=last_error_time,
                    consecutive_failures=data.get("consecutive_failures", 0),
                    is_available=data.get("is_available", True),
                )
                restored_count += 1
        
        log.info(f"Loaded model status cache from {MODEL_STATUS_CACHE_PATH} ({restored_count} entries restored, age: {cache_age:.0f}s)")
        
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in model status cache: {e}")
        # Corrupted cache - try to remove it
        try:
            MODEL_STATUS_CACHE_PATH.unlink()
            log.info(f"Removed corrupted cache file: {MODEL_STATUS_CACHE_PATH}")
        except OSError:
            pass
    except PermissionError as e:
        log.error(f"Permission denied reading model status cache: {e}")
    except OSError as e:
        log.error(f"OS error reading model status cache: {e}")
    except Exception as e:
        log.error(f"Unexpected error loading model status cache: {type(e).__name__}: {e}")


def get_cached_model_status() -> dict[str, Any]:
    """
    Obtener estado cacheado de todos los modelos.
    
    Returns:
        Dict con estado de cada modelo y recomendaciones.
    """
    manager = get_fallback_manager()
    report = manager.get_status_report()
    
    # Añadir información adicional
    report["recommendations"] = []
    
    for agent_id, chain_info in report.get("models", {}).items():
        current = chain_info.get("current")
        available = chain_info.get("available", [])
        
        if not available:
            report["recommendations"].append(
                f"⚠️ {agent_id}: Todos los modelos en cooldown"
            )
        elif current != chain_info.get("chain", [None])[0]:
            report["recommendations"].append(
                f"ℹ️ {agent_id}: Usando fallback {current}"
            )
    
    return report
