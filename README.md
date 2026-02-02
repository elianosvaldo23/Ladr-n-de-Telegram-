# 🤖 Telegram Content Copy Bot

Bot de Telegram avanzado con userbot integrado para copiar contenido de canales con restricciones de protección.

## ✨ Características

### Versión Gratuita
- ✅ Copia de contenido de canales públicos
- ✅ Soporte para múltiples tipos de medios
- ✅ Interfaz intuitiva con comandos

### Versión Premium
- ⭐ Acceso a canales privados
- ⭐ Copia masiva de contenido (hasta 50 mensajes)
- ⭐ Información detallada de canales
- ⭐ Sin límites de uso
- ⭐ Soporte prioritario

## 🔒 Medidas de Seguridad Anti-Ban

Este bot implementa múltiples medidas de seguridad para proteger tu cuenta:

- **Rate Limiting**: Máximo 20 peticiones por minuto
- **Delays Inteligentes**: 2 segundos entre peticiones normales, 3 segundos en copia masiva
- **Gestión de Sesiones**: Uso seguro de StringSession
- **Variables de Entorno**: Tokens protegidos en archivo .env

📖 Lee [SECURITY.md](SECURITY.md) para información detallada sobre seguridad.

## 🚀 Instalación

### 1. Clonar Repositorio

```bash
git clone <url-del-repo>
cd webapp
```

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# Token del Bot de Telegram
BOT_TOKEN=tu_token_de_bot

# API de Telegram para Userbot
API_ID=tu_api_id
API_HASH=tu_api_hash
PHONE_NUMBER=tu_numero_de_telefono

# Usuarios Premium (IDs separados por comas)
PREMIUM_USERS=123456789,987654321

# Configuración de Ambiente
ENVIRONMENT=development
PORT=8080
```

### 4. Obtener Credenciales

#### Bot Token
1. Habla con [@BotFather](https://t.me/BotFather)
2. Crea un nuevo bot con `/newbot`
3. Copia el token proporcionado

#### API ID y Hash
1. Ve a [my.telegram.org](https://my.telegram.org)
2. Inicia sesión con tu número de teléfono
3. Ve a "API development tools"
4. Crea una nueva aplicación
5. Copia el `api_id` y `api_hash`

### 5. Primera Ejecución

```bash
python bot.py
```

En la primera ejecución:
1. Se enviará un código de verificación a tu teléfono
2. Ingresa el código cuando se solicite
3. Si tienes 2FA, ingresa tu contraseña
4. La sesión se guardará automáticamente

## 📋 Comandos Disponibles

### Comandos Básicos
- `/start` - Iniciar el bot y ver información
- `/help` - Ver ayuda y comandos disponibles
- `/status` - Ver tu estado actual (plan, conexión)
- `/premium` - Información sobre la versión premium

### Comandos Premium
- `/info [enlace]` - Ver información detallada del canal
- `/bulk [enlace] [cantidad]` - Copia masiva de contenido (1-50 mensajes)

### Uso Simple
Simplemente envía el enlace del mensaje que deseas copiar:
```
https://t.me/canal/123
```

## 🎯 Tipos de Contenido Soportados

- 📝 Texto y mensajes formateados
- 📸 Imágenes y fotos
- 🎥 Videos
- 📎 Documentos y archivos
- 🎵 Audio y música
- 🎤 Notas de voz
- 🎭 Stickers
- 🎬 GIFs y animaciones

## 🛡️ Seguridad y Privacidad

### Tokens y Credenciales
- ✅ Todos los tokens están en archivo `.env` (no en el código)
- ✅ `.env` está en `.gitignore` (nunca se sube a GitHub)
- ✅ Usa variables de entorno en producción

### Rate Limiting
El bot implementa controles estrictos para evitar bans:

```python
# Configuración de seguridad
min_delay_between_requests = 2.0  # segundos
request_limit_per_minute = 20     # máximo de peticiones
```

### Recomendaciones
1. **No compartas tu archivo .env**
2. **No modifiques los delays de seguridad**
3. **Usa el bot de forma responsable**
4. **Respeta los límites de Telegram**
5. **Lee la documentación de seguridad**

## ⚙️ Configuración Avanzada

### Variables de Entorno

| Variable | Descripción | Requerida | Default |
|----------|-------------|-----------|---------|
| `BOT_TOKEN` | Token del bot de Telegram | ✅ | - |
| `API_ID` | API ID de Telegram | ✅ | - |
| `API_HASH` | API Hash de Telegram | ✅ | - |
| `PHONE_NUMBER` | Número de teléfono del userbot | ✅ | - |
| `PREMIUM_USERS` | IDs de usuarios premium (separados por coma) | ❌ | - |
| `ENVIRONMENT` | Ambiente (development/production) | ❌ | development |
| `PORT` | Puerto para webhook | ❌ | 8080 |
| `WEBHOOK_URL` | URL del webhook (producción) | ❌ | - |

### Modo Producción

Para ejecutar en producción con webhook:

```env
ENVIRONMENT=production
WEBHOOK_URL=https://tu-dominio.com/webhook
```

## 📊 Estructura del Proyecto

```
webapp/
├── bot.py              # Código principal del bot
├── requirements.txt    # Dependencias de Python
├── .env               # Variables de entorno (NO subir a Git)
├── .gitignore         # Archivos ignorados por Git
├── README.md          # Este archivo
└── SECURITY.md        # Documentación de seguridad
```

## 🔧 Troubleshooting

### Error: "Cliente no autorizado"
- Elimina cualquier archivo `.session` existente
- Ejecuta el bot nuevamente y sigue el proceso de autenticación

### Error: "FloodWaitError"
- El bot esperará automáticamente el tiempo requerido
- Reduce la frecuencia de uso
- Los delays están diseñados para evitar esto

### Error: "ChannelPrivateError"
- Asegúrate de estar unido al canal con tu cuenta de userbot
- Verifica que no estés bloqueado del canal
- Los canales privados requieren versión Premium

### Bot no responde
- Verifica que el token sea correcto
- Comprueba tu conexión a internet
- Revisa los logs para errores

## 📝 Logs

El bot genera logs detallados:

```python
# Los logs se muestran en consola
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
```

Para guardar logs en archivo:

```python
# Agregar en la configuración de logging
filename='bot.log'
```

## ⚠️ Limitaciones y Consideraciones

### Límites de Telegram
- **Lectura**: ~20 mensajes por minuto (implementado)
- **Envío**: ~30 mensajes por segundo (diferentes chats)
- **Mismo chat**: ~1 mensaje por segundo

### Consideraciones Legales
- Respeta los derechos de autor
- No copies contenido privado sin permiso
- Usa el bot de forma ética y legal
- El bot es solo para fines educativos

### Rendimiento
- La copia masiva puede ser lenta (por seguridad)
- Videos grandes pueden tardar en procesarse
- Algunos tipos de mensajes pueden no ser soportados

## 🤝 Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## ⚡ Tecnologías Utilizadas

- [python-telegram-bot](https://python-telegram-bot.org/) - Framework del bot
- [Telethon](https://docs.telethon.dev/) - Cliente de Telegram (userbot)
- [python-dotenv](https://pypi.org/project/python-dotenv/) - Gestión de variables de entorno
- [asyncio](https://docs.python.org/3/library/asyncio.html) - Programación asíncrona

## 📞 Soporte

Si necesitas ayuda:
1. Revisa la [documentación de seguridad](SECURITY.md)
2. Revisa la sección de Troubleshooting
3. Abre un issue en GitHub
4. Contacta al administrador

## 🎯 Roadmap

- [ ] Sistema de queue para peticiones
- [ ] Persistencia de sesión en base de datos
- [ ] Dashboard web para estadísticas
- [ ] Soporte para más tipos de medios
- [ ] Sistema de plugins
- [ ] API REST para integraciones

---

**⚠️ Disclaimer**: Este bot es solo para fines educativos. Usa bajo tu propia responsabilidad y respeta los términos de servicio de Telegram.
