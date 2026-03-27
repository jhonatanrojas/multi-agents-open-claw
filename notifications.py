"""
notifications.py - Sistema de Notificaciones Inteligentes

Implementa reglas para notificar solo eventos relevantes por Telegram,
evitando spam de rate limits con fallback exitoso o reintentos.

Uso:
    from notifications import NotificationManager, should_notify
    
    manager = NotificationManager()
    manager.notify("project_delivered", "Proyecto entregado: Mi App")
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from enum import Enum

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# ── Categorías de Notificación ─────────────────────────────────────────────────

class NotificationCategory(Enum):
    PROJECT_DELIVERED = "project_delivered"
    CRITICAL_ERROR = "critical_error"
    BLOCKED_WAITING_USER = "blocked_waiting_user"
    TASK_COMPLETED = "task_completed"
    PHASE_COMPLETED = "phase_completed"
    MODEL_FALLBACK = "model_fallback"
    RATE_LIMIT = "rate_limit"
    RETRY_ATTEMPT = "retry_attempt"
    PROGRESS_UPDATE = "progress_update"


# ── Reglas de Notificación ─────────────────────────────────────────────────────

# always: Siempre notificar
# never: Nunca notificar  
# throttled: Notificar máximo una vez por período

NOTIFICATION_RULES: dict[str, dict[str, Any]] = {
    # Eventos importantes - siempre notificar
    NotificationCategory.PROJECT_DELIVERED.value: {
        "policy": "always",
        "emoji": "✅",
        "template": "Proyecto entregado: {name}\n{summary}",
    },
    NotificationCategory.CRITICAL_ERROR.value: {
        "policy": "always",
        "emoji": "🚨",
        "template": "Error crítico: {error}\nProyecto: {project_name}",
    },
    NotificationCategory.BLOCKED_WAITING_USER.value: {
        "policy": "always",
        "emoji": "⏸️",
        "template": "Bloqueado esperando respuesta:\n{question}",
    },
    
    # Eventos throttled - máximo 1 por minuto
    NotificationCategory.TASK_COMPLETED.value: {
        "policy": "throttled",
        "throttle_seconds": 60,
        "emoji": "✓",
        "template": "Tarea {task_id} completada por {agent}",
    },
    NotificationCategory.PHASE_COMPLETED.value: {
        "policy": "throttled",
        "throttle_seconds": 120,
        "emoji": "📋",
        "template": "Fase {phase_name} completada",
    },
    
    # Eventos que NO notificar
    NotificationCategory.MODEL_FALLBACK.value: {
        "policy": "never",
        "reason": "Fallback exitoso, no requiere intervención",
    },
    NotificationCategory.RATE_LIMIT.value: {
        "policy": "never", 
        "reason": "Rate limits con fallback no requieren acción",
    },
    NotificationCategory.RETRY_ATTEMPT.value: {
        "policy": "never",
        "reason": "Reintentos automáticos son normales",
    },
    NotificationCategory.PROGRESS_UPDATE.value: {
        "policy": "never",
        "reason": "Actualizaciones de progreso son muy frecuentes",
    },
}


@dataclass
class NotificationState:
    """Estado de notificaciones para throttling."""
    last_notification: dict[str, float] = field(default_factory=dict)
    notification_counts: dict[str, int] = field(default_factory=dict)


class NotificationManager:
    """
    Gestor de notificaciones con reglas inteligentes.
    
    Aplica políticas de notificación basadas en la categoría del evento:
    - always: Siempre envía notificación
    - never: Nunca envía notificación
    - throttled: Envía máximo una por período configurado
    """
    
    def __init__(
        self,
        rules: dict[str, Any] | None = None,
        throttle_seconds: int = 60,
    ):
        self.rules = rules or NOTIFICATION_RULES
        self.throttle_seconds = throttle_seconds
        self._state = NotificationState()
    
    def should_notify(self, category: str) -> tuple[bool, str | None]:
        """
        Determinar si se debe enviar notificación.
        
        Args:
            category: Categoría del evento
            
        Returns:
            Tupla (should_send, reason_if_skipped)
        """
        rule = self.rules.get(category)
        
        if not rule:
            # Categoría desconocida - permitir con throttle
            return self._check_throttle(category, self.throttle_seconds)
        
        policy = rule.get("policy", "throttled")
        
        if policy == "always":
            return (True, None)
        
        if policy == "never":
            return (False, rule.get("reason", "Política: never"))
        
        if policy == "throttled":
            throttle_sec = rule.get("throttle_seconds", self.throttle_seconds)
            return self._check_throttle(category, throttle_sec)
        
        return (True, None)
    
    def _check_throttle(self, category: str, seconds: int) -> tuple[bool, str | None]:
        """Verificar si ha pasado suficiente tiempo desde la última notificación."""
        now = time.time()
        last_time = self._state.last_notification.get(category, 0)
        elapsed = now - last_time
        
        if elapsed >= seconds:
            return (True, None)
        
        remaining = int(seconds - elapsed)
        return (False, f"Throttled: espera {remaining}s más")
    
    def record_notification(self, category: str) -> None:
        """Registrar que se envió una notificación."""
        now = time.time()
        self._state.last_notification[category] = now
        self._state.notification_counts[category] = \
            self._state.notification_counts.get(category, 0) + 1
    
    def format_message(self, category: str, **kwargs: Any) -> str:
        """
        Formatear mensaje según plantilla de la categoría.
        
        Args:
            category: Categoría del evento
            **kwargs: Variables para la plantilla
            
        Returns:
            Mensaje formateado
        """
        rule = self.rules.get(category, {})
        template = rule.get("template", "{message}")
        emoji = rule.get("emoji", "")
        
        try:
            message = template.format(**kwargs)
            if emoji:
                return f"{emoji} {message}"
            return message
        except KeyError as e:
            # Fallback si faltan variables
            return f"{emoji} [{category}] {kwargs}" if emoji else f"[{category}] {kwargs}"
    
    def notify(
        self,
        category: str,
        send_func: Callable[[str], dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Notificar si la política lo permite.
        
        Args:
            category: Categoría del evento
            send_func: Función para enviar (ej: send_telegram_message)
            **kwargs: Variables para el mensaje
            
        Returns:
            Dict con resultado del envío
        """
        should_send, reason = self.should_notify(category)
        
        if not should_send:
            log.debug(f"[notifications] Skipped {category}: {reason}")
            return {
                "sent": False,
                "reason": reason,
                "category": category,
            }
        
        message = self.format_message(category, **kwargs)
        
        if send_func:
            result = send_func(message)
        else:
            # Loguear si no hay función de envío
            log.info(f"[notifications] {message}")
            result = {"sent": True, "method": "log"}
        
        if result.get("sent"):
            self.record_notification(category)
        
        return result
    
    def get_stats(self) -> dict[str, Any]:
        """Obtener estadísticas de notificaciones."""
        return {
            "counts": dict(self._state.notification_counts),
            "last_notifications": {
                k: int(v) for k, v in self._state.last_notification.items()
            },
        }


# ── Instancia global ───────────────────────────────────────────────────────────

_notification_manager: NotificationManager | None = None


def get_notification_manager() -> NotificationManager:
    """Obtener instancia singleton del gestor de notificaciones."""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


def should_notify(category: str) -> tuple[bool, str | None]:
    """Función de conveniencia para verificar si notificar."""
    return get_notification_manager().should_notify(category)


def notify(
    category: str,
    send_func: Callable[[str], dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Función de conveniencia para enviar notificación."""
    return get_notification_manager().notify(category, send_func, **kwargs)


def format_notification(category: str, **kwargs: Any) -> str:
    """Función de conveniencia para formatear mensaje."""
    return get_notification_manager().format_message(category, **kwargs)
