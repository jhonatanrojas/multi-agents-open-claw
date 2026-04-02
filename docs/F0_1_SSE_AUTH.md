# F0.1 — Fix autenticación SSE

## Resumen

Implementación de autenticación basada en cookies para endpoints SSE y WebSocket, permitiendo reconexiones automáticas sin intervención del usuario incluso después de reinicios del gateway.

## Problema resuelto

El stream SSE no sobrevivía reinicios de sesión ni proxies porque:
1. Las sesiones se almacenaban solo en memoria
2. Al reiniciar el gateway, todas las sesiones se perdían
3. Los clientes tenían que volver a autenticarse manualmente

## Solución implementada

### 1. Persistencia de sesiones (F0.1-FINAL)

Las sesiones ahora se persisten en `MEMORY.json` para sobrevivir reinicios del gateway:

```python
# En dashboard_api.py
_SESSION_STATE_KEY = "_sessions"  # Key in MEMORY.json

def _load_sessions_from_memory():
    """Load persisted sessions from MEMORY.json on startup."""
    # Carga sesiones válidas al iniciar
    
def _save_sessions_to_memory():
    """Save active sessions to MEMORY.json."""
    # Guarda sesiones en cada cambio
```

**Flujo de persistencia:**
1. Al crear sesión → se guarda en MEMORY.json
2. Al validar sesión → se recarga desde MEMORY.json
3. Al limpiar sesiones expiradas → se actualiza MEMORY.json

### 2. Nuevos endpoints de autenticación

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/auth/login` | POST | Crea sesión y setea cookie HttpOnly |
| `/api/auth/logout` | POST | Invalida la sesión actual |
| `/api/auth/session` | GET | Verifica si la sesión es válida |

### 3. Endpoints soportados con cookie auth

- `GET /api/stream` — SSE stream
- `WS /ws/state` — WebSocket de estado
- `WS /ws/gateway-events` — WebSocket de eventos gateway

### 4. Configuración de cookies

```python
{
    'HttpOnly': True,      # JavaScript no puede leerla
    'Secure': True,        # Solo HTTPS (excepto localhost)
    'SameSite': 'Strict',  # Protección CSRF
    'Path': '/',           # Disponible en todo el sitio
    'Max-Age': 86400,      # 24 horas (configurable)
}
```

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DASHBOARD_API_KEY` | "" | API key para autenticación header |
| `DASHBOARD_SESSION_SECRET` | derivado de API key | Secret para firmar sesiones |
| `DASHBOARD_SESSION_MAX_AGE` | 86400 | Duración de sesión en segundos |
| `DASHBOARD_ALLOWED_ORIGINS` | "*" | Orígenes CORS permitidos |

## Flujo de uso

### 1. Autenticación inicial (browser)

```javascript
// 1. Login con API key
const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: 'tu-api-key' }),
    credentials: 'include'  // Importante: incluir cookies
});

// 2. Cookie se setea automáticamente por el navegador
```

### 2. Conexión SSE (browser)

```javascript
// El navegador envía la cookie automáticamente
const eventSource = new EventSource('/api/stream', {
    withCredentials: true  // Importante: incluir cookies
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('State update:', data);
};

// Reconexión automática: el navegador reenvía la cookie
// Incluso después de reinicio del gateway, la sesión persiste
```

### 3. WebSocket (browser)

```javascript
// El navegador envía cookies en el handshake
const ws = new WebSocket('ws://localhost:8000/ws/state');

ws.onopen = () => console.log('Connected with cookie auth');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Update:', data);
};
```

## Frontend: Manejo de reconexión

El hook `useSSE` ahora incluye:

1. **Verificación de sesión**: Antes de conectar, verifica que la sesión sea válida
2. **Reconexión automática**: Con backoff exponencial y jitter
3. **Persistencia de Last-Event-ID**: Para reanudar el stream desde donde se quedó
4. **Manejo de errores 401**: Redirige a login cuando la sesión expira

```typescript
// useSSE.ts
const reconnectAttempts = 0;
const maxReconnectAttempts = 10;
const baseReconnectDelay = 1000;
const maxReconnectDelay = 30000;

// Exponential backoff with jitter
const delay = Math.min(
    baseReconnectDelay * Math.pow(2, reconnectAttempts - 1),
    maxReconnectDelay
);
const jitter = Math.random() * 1000;
```

## Seguridad

### Cookie HttpOnly
- Previene acceso JavaScript a la cookie de sesión
- Mitiga ataques XSS

### Secure flag
- Cookie solo se envía por HTTPS en producción
- En localhost se permite HTTP para desarrollo

### SameSite=Strict
- Protección contra CSRF
- Cookie solo se envía a requests del mismo sitio

### Persistencia segura
- Las sesiones se guardan en MEMORY.json con timestamp
- Al cargar, se filtran las sesiones expiradas
- No se guardan secrets ni datos sensibles

## Tests

```bash
# Tests unitarios
cd /var/www/openclaw-multi-agents
python3 tests/test_f0_1_auth.py

# Tests de integración
python3 tests/test_f0_1_integration.py
```

## Archivos modificados

| Archivo | Cambios |
|---------|---------|
| `dashboard_api.py` | Persistencia de sesiones, endpoints auth, middleware |
| `frontend/src/hooks/useSSE.ts` | Reconexión automática con verificación de sesión |
| `frontend/src/api/client.ts` | Manejo de errores 401, credentials include |
| `frontend/src/store/authStore.ts` | Gestión de autenticación y sesiones |

## Criterio de aceptación

✅ **Cumplido**: El stream SSE reconecta automáticamente después de un reinicio de gateway sin intervención del usuario.

**Evidencia:**
1. Las sesiones se persisten en MEMORY.json
2. Al reiniciar el gateway, las sesiones válidas se restauran
3. El cliente reconecta automáticamente con la misma cookie
4. Los tests de integración verifican este comportamiento

## Notas de implementación

- **Fase 0 (original)**: Implementación básica de cookies en memoria
- **Fase 1 (esta corrección)**: Agregada persistencia en MEMORY.json para sobrevivir reinicios
- **Compatibilidad**: El cambio es transparente para el frontend existente
- **Rendimiento**: La carga de sesiones ocurre solo al validar, minimizando I/O