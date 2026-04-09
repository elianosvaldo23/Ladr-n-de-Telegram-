# 🤖 Telegram Content Copy Bot

Bot de Telegram avanzado con userbot integrado para copiar contenido de canales con restricciones de protección.

## ✨ Características

### Versión Gratuita
- ✅ Copia de contenido de canales públicos
- ✅ Soporte para múltiples tipos de medios
- ✅ Interfaz intuitiva con botones

### Versión Premium
- ⭐ Acceso a canales privados
- ⭐ Copia masiva de contenido (hasta 50 mensajes)
- ⭐ Información detallada de canales
- ⭐ Sin límites de uso
- ⭐ Soporte prioritario

## 🆕 Novedades de esta Versión

### 🚀 Optimizaciones de Velocidad (NUEVO)

#### ⚡ Sistema Inteligente de Reenvío de 2 Capas
1. **Forward Directo** (INSTANTÁNEO) 🚀
   - Para canales **SIN** restricción de reenvío
   - **Sin descarga** - reenvío directo en segundos
   - Preserva todo: miniatura, metadatos, calidad original
   - Ahorra tiempo y ancho de banda
   
2. **Descarga Optimizada** (Cuando es necesario) 📥📤
   - Para canales **CON** protección de contenido
   - Velocidades optimizadas con conexiones TCP
   - Progreso en tiempo real cada 10MB
   - Cancelación instantánea disponible

#### ✅ Mejoras Técnicas
- **URLs mejoradas**: Soporte completo para `https://t.me/c/{channel_id}/{message_id}`
- **Velocidad aumentada**: Configuraciones optimizadas de Telethon
- **Detección inteligente**: Identifica automáticamente si puede usar forward directo
- **Sin descargas innecesarias**: Solo descarga cuando es estrictamente necesario

### ⚙️ Configuración del Userbot desde Telegram
- **Ya NO necesitas editar el archivo `.env`** para las credenciales del userbot
- Configuración guiada paso a paso desde el bot
- Sistema seguro de almacenamiento de credenciales
- Soporte para 2FA (autenticación de dos factores)

### 🎯 Interfaz Mejorada
- Todos los comandos (excepto `/start`) convertidos a **botones interactivos**
- Menú principal con acceso rápido a todas las funciones
- Navegación intuitiva

### 🔧 Administración Simplificada
- Panel de configuración exclusivo para administradores
- Prueba de conexión del userbot
- Reconfiguración fácil en cualquier momento

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

# ID del Administrador (puede configurar el userbot)
ADMIN_ID=tu_user_id

# Usuarios Premium (IDs separados por comas)
PREMIUM_USERS=123456789,987654321

# Configuración de Ambiente
ENVIRONMENT=development
PORT=8080

# NOTA: Las credenciales del userbot (API_ID, API_HASH, PHONE_NUMBER)
# ahora se configuran desde el bot usando el menú de configuración.
```

### 4. Obtener Bot Token

1. Habla con [@BotFather](https://t.me/BotFather)
2. Crea un nuevo bot con `/newbot`
3. Copia el token proporcionado
4. Añádelo al archivo `.env` como `BOT_TOKEN`

### 5. Obtener tu User ID

1. Habla con [@userinfobot](https://t.me/userinfobot)
2. El bot te dará tu User ID
3. Añádelo al archivo `.env` como `ADMIN_ID`

### 6. Primera Ejecución

```bash
python bot.py
```

### 7. Configurar el Userbot (Desde Telegram)

La configuración del userbot ahora se hace **completamente desde Telegram**:

1. Inicia el bot con `/start`
2. Toca el botón "⚙️ Configurar Userbot"
3. El bot te pedirá paso a paso:
   - **API ID**: Obtener en [my.telegram.org](https://my.telegram.org)
   - **API Hash**: Obtener en [my.telegram.org](https://my.telegram.org)
   - **Número de teléfono**: Con código de país (ej: +1234567890)
   - **Código de verificación**: Se enviará a tu Telegram
   - **Contraseña 2FA**: Si tienes autenticación de dos factores

4. Una vez configurado, el bot estará listo para usar

**Ventajas de este método:**
- ✅ No necesitas editar archivos de configuración
- ✅ Configuración guiada paso a paso
- ✅ Las credenciales se almacenan de forma segura
- ✅ Puedes reconfigurar en cualquier momento

#### Obtener API ID y API Hash

1. Ve a [my.telegram.org](https://my.telegram.org)
2. Inicia sesión con tu número de teléfono
3. Ve a "API development tools"
4. Crea una nueva aplicación
5. Copia el `api_id` y `api_hash`

## 📋 Uso del Bot

### Menú Principal
El bot ahora usa un **sistema de botones interactivo**. Al usar `/start`, verás botones para:

- **📋 Ayuda**: Ver información de uso y formatos soportados
- **📊 Mi Estado**: Ver tu plan, estado de conexión y funciones disponibles
- **⭐ Premium**: Información sobre la versión premium
- **📊 Info de Canal** (Premium): Ver detalles de canales
- **⚙️ Configurar Userbot** (Solo Admin): Configurar credenciales del userbot

### Copia Simple
Simplemente envía el enlace del mensaje que deseas copiar:
```
https://t.me/canal/123
```

### Copia Masiva (Premium)
Envía el enlace del canal seguido de la cantidad de mensajes:
```
https://t.me/canal 10
```
Límite: 1-50 mensajes

### Información de Canal (Premium)
Envía solo el enlace del canal (sin número de mensaje):
```
https://t.me/canal
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
- ✅ Token del bot en archivo `.env` (no en el código)
- ✅ Credenciales del userbot en archivo JSON cifrado
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
2. **No compartas el archivo userbot_config.json**
3. **No modifiques los delays de seguridad**
4. **Usa el bot de forma responsable**
5. **Respeta los límites de Telegram**
6. **Lee la documentación de seguridad**

## ⚙️ Configuración Avanzada

### Variables de Entorno

| Variable | Descripción | Requerida | Default |
|----------|-------------|-----------|---------|
| `BOT_TOKEN` | Token del bot de Telegram | ✅ | - |
| `ADMIN_ID` | User ID del administrador | ✅ | - |
| `PREMIUM_USERS` | IDs de usuarios premium (separados por coma) | ❌ | - |
| `ENVIRONMENT` | Ambiente (development/production) | ❌ | development |
| `PORT` | Puerto para webhook | ❌ | 8080 |
| `WEBHOOK_URL` | URL del webhook (producción) | ❌ | - |

**NOTA**: Las credenciales del userbot (API_ID, API_HASH, PHONE_NUMBER) ya no se configuran en el `.env`. Ahora se configuran desde el bot usando el menú interactivo.

### Modo Producción

Para ejecutar en producción con webhook:

```env
ENVIRONMENT=production
WEBHOOK_URL=https://tu-dominio.com/webhook
```

## 📊 Estructura del Proyecto

**Estructura plana** (sin subcarpetas) para facilitar la descarga y subida manual al VPS:

```
webapp/
├── bot.py              # Punto de entrada principal
├── copy_bot.py         # ContentCopyBot y UserbotConfig (Pyrogram)
├── state.py            # Estado global (instancias db, copy_bot)
├── database.py         # Operaciones MongoDB
├── start_handler.py    # Comando /start y menú principal
├── button_handler.py   # Callbacks de botones inline
├── link_handler.py     # Procesamiento de enlaces de Telegram
├── config_handler.py   # Conversación de configuración del userbot
├── admin_handler.py    # Acciones de admin (premium, broadcast)
├── config.py           # Constantes de configuración
├── exceptions.py       # Excepciones personalizadas
├── logging_utils.py    # Configuración de logging
├── memory.py           # Monitoreo de memoria y disco
├── progress.py         # Tracker de progreso de transferencias
├── strings.py          # Textos centralizados de la UI
├── requirements.txt    # Dependencias de Python
├── .env                # Variables de entorno (NO subir a Git)
├── .gitignore          # Archivos ignorados por Git
├── README.md           # Este archivo
└── SECURITY.md         # Documentación de seguridad
```

## 🔧 Troubleshooting

### Error: "Userbot no configurado"
- El administrador debe configurar el userbot desde el menú
- Usa el botón "⚙️ Configurar Userbot" en el menú principal
- Sigue el proceso guiado de configuración

### Error: "Código inválido"
- Verifica que hayas copiado el código correctamente
- El código tiene un tiempo de expiración, solicita uno nuevo si es necesario
- Asegúrate de no incluir espacios adicionales

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
- Verifica que el userbot esté configurado

### Problemas de Configuración del Userbot
- Verifica que tu API ID y API Hash sean correctos
- Asegúrate de que el número de teléfono incluya el código de país
- Si tienes 2FA, asegúrate de ingresar la contraseña correcta
- Usa el botón "🔄 Reconfigurar" para empezar de nuevo

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

- [x] Sistema de configuración desde el bot
- [x] Interfaz basada en botones inline
- [x] Almacenamiento seguro de credenciales
- [ ] Sistema de queue para peticiones
- [ ] Dashboard web para estadísticas
- [ ] Soporte para más tipos de medios
- [ ] Sistema de plugins
- [ ] API REST para integraciones

---

**⚠️ Disclaimer**: Este bot es solo para fines educativos. Usa bajo tu propia responsabilidad y respeta los términos de servicio de Telegram.
