# Informe de Cambios — Colibry Bot Server
**Fecha:** 2026-03-24
**Servidor:** Hetzner — 178.104.58.204
**Proyecto:** `/root/sprin_03/`
**Responsable:** Claude Code (claude-sonnet-4-6)

---

## 1. Panel de Control Móvil — Ruta `/status`

### Descripción
Se agregó una ruta `/status` directamente al archivo `bot_server.py` existente (sin crear una nueva aplicación Flask). El panel es accesible desde cualquier dispositivo móvil o navegador con autenticación básica HTTP.

### Archivos modificados
| Archivo | Acción | Tamaño final |
|---|---|---|
| `/root/sprin_03/bot_server.py` | Modificado — agregadas 3 funciones + 1 ruta | 18,498 bytes / 485 líneas |
| `/root/sprin_03/templates/status.html` | Creado nuevo | 4,698 bytes |

### Código agregado a `bot_server.py`
Se añadieron los siguientes imports al bloque existente:
```python
from flask import Flask, Response, jsonify, render_template, request  # +Response
import socket        # para verificar puertos
import subprocess    # para leer uptime
from functools import wraps  # para el decorador de auth
```

Se agregaron 4 bloques funcionales antes del bloque `if __name__ == "__main__":`:

**a) Autenticación básica HTTP**
```python
_STATUS_USER = "aton2026"
_STATUS_PASS = "Dispatch2026"

def _require_auth(f):
    # Decorador — retorna 401 si credenciales incorrectas
    # Realm: "Colibry Panel"
```

**b) Verificación de puertos**
```python
def _port_open(port, host="127.0.0.1", timeout=1):
    # Intenta socket.create_connection() — retorna True/False
```
Puertos monitoreados:
- Evolution API: `8080`
- Flowise: `3000`, `3001`, `8888`, `4000` (detecta el primero activo)
- n8n: `5678`, `3001`, `3000` (detecta el primero activo)

**c) Parser de log**
```python
def _parse_log():
    # Lee bot.log línea por línea
    # Cuenta mensajes hoy (líneas con "/ejecutar" + fecha actual)
    # Extrae últimas 10 invocaciones de herramientas ([TOOL])
    # Retorna: msgs_today, last_msg, tools_used[-10:]
```

**d) Ruta `/status`**
```python
@app.route("/status")
@_require_auth
def status_panel():
    # Renderiza templates/status.html con contexto:
    # bot_ok, evolution_ok, flowise_ok/port, n8n_ok/port,
    # msgs_today, last_msg, tools, uptime, now
```

### Template `status.html`
- **Mobile-first** — max-width 600px, compatible con pantallas de 360px+
- **Dark theme** — consistente con `index.html` (gradiente `#1a1a2e → #0f3460`)
- Bootstrap 5.3.3 CDN
- Indicadores visuales con punto de color (verde pulsante = activo, rojo = inactivo)
- Auto-refresh por botón (no polling automático para no saturar el servidor)

Secciones del panel:
1. Estado Bot Colibry (activo/inactivo + puerto)
2. Métricas: mensajes hoy + tareas recientes
3. Último mensaje recibido (timestamp)
4. Estado de servicios: Evolution API, Flowise, n8n
5. Tareas Dispatch (últimas 10 invocaciones de herramientas)
6. Uptime del servidor

### Acceso
```
URL: https://gossip-yale-courage-francis.trycloudflare.com/status
Usuario: aton2026
Contraseña: Dispatch2026
```

---

## 2. Túnel Cloudflare — Acceso Público Seguro

### Descripción
Se instaló `cloudflared` y se configuró como servicio `systemd` para exponer el puerto 5000 de Flask a través de una URL HTTPS pública sin abrir puertos en el firewall del servidor.

### Instalación
```bash
# Repositorio oficial de Cloudflare
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg

echo "deb [signed-by=...] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  > /etc/apt/sources.list.d/cloudflared.list

apt-get update && apt-get install -y cloudflared
# Versión instalada: 2026.3.0 (build 2026-03-09)
```

### Servicio systemd
Archivo: `/etc/systemd/system/cloudflared.service`

```ini
[Unit]
Description=Cloudflare Tunnel — Colibry Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/sprin_03
ExecStart=/usr/bin/cloudflared tunnel --url http://localhost:5000 --no-autoupdate
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable cloudflared   # arranca en cada reboot
systemctl start cloudflared    # iniciado: 2026-03-24 17:26:52 UTC
```

### Estado actual
| Parámetro | Valor |
|---|---|
| Estado systemd | `active (running)` |
| Habilitado en boot | Sí (`enabled`) |
| Tipo de túnel | Quick Tunnel (trycloudflare.com) |
| URL pública actual | `https://gossip-yale-courage-francis.trycloudflare.com` |
| Logs | `journalctl -u cloudflared -f` |

### Limitación conocida
La URL `*.trycloudflare.com` es **dinámica** — cambia si el servicio se reinicia o el servidor se apaga. Para URL permanente se requiere una cuenta Cloudflare y un Named Tunnel configurado.

Para consultar la URL activa en cualquier momento:
```bash
journalctl -u cloudflared -n 20 | grep trycloudflare
```

---

## 3. Script `check_status.sh`

### Descripción
Script bash de diagnóstico rápido del sistema completo.

### Archivo
```
/root/sprin_03/check_status.sh
chmod +x  ✔
Tamaño: 3,668 bytes
```

### Uso
```bash
./check_status.sh
# o desde cualquier directorio:
bash /root/sprin_03/check_status.sh
```

### Secciones que reporta
| # | Sección | Qué detecta |
|---|---|---|
| 1 | Proceso Python | PID de bot_server.py via `pgrep` |
| 2 | Dispatch / Tareas | Conteo de `[TOOL]` en bot.log + últimas 5 |
| 3 | Evolution API | Puerto 8080 via `nc` |
| 4 | Flowise | Puertos 3000, 3001, 8888, 4000 + proceso node |
| 5 | n8n | Puertos 5678, 3001, 3000 + proceso node |
| 6 | Cloudflare Tunnel | Estado systemd + URL activa via journalctl |
| 7 | Log (últimas 20 líneas) | `tail -20 bot.log` |
| 8 | Mensajes hoy | Count de `/ejecutar` con fecha de hoy |
| 9 | Uptime | `uptime` del sistema |

---

## 4. OpenAI TTS — Funcionalidad Existente (Revisión)

### Descripción
La funcionalidad de Text-to-Speech ya estaba implementada en `bot_server.py` desde la versión anterior. Se documenta aquí para dejar registro de su funcionamiento.

### Implementación
```python
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "300"))

def _generate_tts(phone: str, text: str) -> str | None:
```

### Lógica
1. Si `len(text) > TTS_MAX_CHARS` (default 300) → **omite TTS** (evita costos en respuestas largas)
2. Genera nombre de archivo: `audio_{phone_sanitizado}_{timestamp}.mp3`
3. Llama `client.audio.speech.create(model="tts-1", voice="nova", input=text)`
4. Escribe el archivo con `response.stream_to_file(audio_path)`
5. Retorna la ruta del `.mp3` o `None` si falla

### Integración con el agente
```python
# En run_agent():
audio_path = _generate_tts(phone, reply) if reply and not is_error else None

return {
    "reply":      reply,
    "audio_path": audio_path,   # ← ruta del .mp3 o None
    "tool_used":  tool_used,
}
```

### Manejo de errores
| Error | Comportamiento |
|---|---|
| `APIError` | Log warning — retorna `None` (no crítico) |
| Cualquier excepción | Log warning — retorna `None` (no crítico) |
| Respuesta con ⚠️ o 🙏 (error) | TTS omitido automáticamente |

### Modelo y voz
| Parámetro | Valor |
|---|---|
| Modelo | `tts-1` (estándar, menor costo) |
| Voz | `nova` (femenina, natural) |
| Formato | `.mp3` |
| Límite configurable | `TTS_MAX_CHARS` en `.env` (default 300) |

### Estado actual
- El endpoint `/ejecutar` retorna `audio_path` en el JSON de respuesta
- Los archivos `.mp3` se generan en el directorio de trabajo (`/root/sprin_03/`)
- **Pendiente:** limpiar archivos de audio antiguos (no hay rotación implementada)
- **Pendiente:** integrar envío del audio por WhatsApp/Evolution API (actualmente solo genera el archivo)

---

## Resumen de Archivos Afectados

| Archivo | Tipo | Acción |
|---|---|---|
| `/root/sprin_03/bot_server.py` | Python/Flask | Modificado (+130 líneas) |
| `/root/sprin_03/templates/status.html` | HTML/Jinja2 | Creado |
| `/root/sprin_03/check_status.sh` | Bash | Creado |
| `/etc/systemd/system/cloudflared.service` | systemd unit | Creado |
| `/etc/apt/sources.list.d/cloudflared.list` | APT repo | Creado |
| `/usr/share/keyrings/cloudflare-main.gpg` | GPG key | Creado |

## Estado del Sistema Post-Cambios

```
Flask bot_server.py   → ACTIVO  (PID 111580, puerto 5000)
Evolution API Docker  → ACTIVO  (puerto 8080)
PostgreSQL Docker     → ACTIVO  (puerto 5432)
Redis Docker          → ACTIVO
cloudflared           → ACTIVO  (systemd, URL pública generada)
Flowise               → INACTIVO (no detectado)
n8n                   → INACTIVO (no detectado)
```
