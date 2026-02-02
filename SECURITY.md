# Medidas de Seguridad Anti-Ban - Telegram Userbot

## 🛡️ Implementaciones de Seguridad

### 1. Rate Limiting Inteligente
El bot implementa un sistema de control de tasa de peticiones para evitar el banneo de la cuenta:

- **Delay mínimo entre peticiones**: 2 segundos entre cada petición a la API de Telegram
- **Límite por minuto**: Máximo 20 peticiones por minuto
- **Limpieza automática**: El sistema limpia el historial de peticiones cada minuto

### 2. Variables de Entorno Seguras
Todos los tokens y credenciales están almacenados en archivo `.env`:

```env
BOT_TOKEN=tu_token_aqui
API_ID=tu_api_id
API_HASH=tu_api_hash
PHONE_NUMBER=tu_telefono
```

**⚠️ IMPORTANTE**: El archivo `.env` está en `.gitignore` y NUNCA debe subirse a GitHub.

### 3. Control de Copia Masiva
Para operaciones de copia masiva:

- **Delay aumentado**: 3 segundos entre cada mensaje copiado
- **Límite de mensajes**: Máximo 50 mensajes por operación
- **Logs detallados**: Registro de todas las operaciones para monitoreo

### 4. Gestión de Sesiones
- Uso de `StringSession` para mantener la sesión persistente
- Reconexión automática en caso de desconexión
- Manejo de errores de autenticación

## 🔒 Configuración de Tokens

### Tokens Actualizados

Los tokens han sido actualizados en el archivo `.env`:

```
BOT_TOKEN: 8243952025:AAGBsFfvTTkTKvjYO1POSiEyma2OdKmmGH8
API_ID: 29432896
API_HASH: 1c8c35a891dcfb84e4ad96f826cdad85
```

## 📋 Recomendaciones de Uso Seguro

### 1. Evitar Spam
- No realizar más de 20 peticiones por minuto
- Respetar los delays automáticos del bot
- No usar la copia masiva frecuentemente

### 2. Uso Responsable
- Solo copiar contenido de canales donde tengas permiso
- Respetar derechos de autor
- No compartir contenido privado sin autorización

### 3. Monitoreo
- Revisar logs regularmente: `logs/*.log`
- Estar atento a warnings de rate limiting
- Si recibes errores de FloodWait, el bot esperará automáticamente

### 4. Límites de Telegram
Telegram impone límites estrictos:

- **Mensajes**: ~30 mensajes/segundo en diferentes chats
- **Mismo chat**: ~1 mensaje/segundo
- **Lectura de mensajes**: ~20 peticiones/minuto (implementado en el bot)
- **FloodWait**: Si excedes límites, Telegram puede bloquearte temporalmente

## ⚙️ Funciones de Seguridad Implementadas

### `rate_limit_check()`
Función que controla el rate limiting:

```python
async def rate_limit_check(self):
    """Control de rate limiting para evitar ban de Telegram"""
    # Limpia peticiones antiguas
    # Verifica límite por minuto
    # Aplica delay mínimo entre peticiones
    # Registra cada petición
```

### Características:
- ✅ Limpieza automática de historial
- ✅ Wait automático si se alcanza el límite
- ✅ Logging de warnings
- ✅ Contador de peticiones

## 🚀 Cómo Iniciar el Bot de Forma Segura

### 1. Configurar Variables de Entorno

```bash
# Editar .env con tus credenciales
nano .env
```

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 3. Primera Ejecución

```bash
python bot.py
```

En la primera ejecución, necesitarás:
1. Ingresar el código de verificación de Telegram
2. Si tienes 2FA, ingresar tu contraseña
3. La sesión se guardará automáticamente

### 4. Verificar Funcionamiento

Envía `/status` al bot para verificar:
- Estado de conexión del cliente
- Plan del usuario (Premium/Gratuito)
- Funciones disponibles

## 🔍 Detección de Problemas

### Señales de Warning
Si ves estos mensajes, reduce el uso:

```
⚠️ Rate limit alcanzado. Esperando X segundos...
```

### FloodWaitError
Si recibes este error:
- El bot esperará automáticamente el tiempo requerido
- No intentes hacer más peticiones manualmente
- Espera a que el bot se recupere

### ChannelPrivateError
Si recibes este error:
- Asegúrate de estar unido al canal con tu userbot
- Verifica que el canal no te haya bloqueado
- Algunos canales privados requieren invitación

## 📊 Estadísticas de Seguridad

El bot registra:
- Total de peticiones realizadas
- Tiempo entre peticiones
- Peticiones por minuto
- Warnings de rate limiting

## ⚠️ Advertencias Importantes

1. **No modifiques los delays**: Los valores están optimizados para seguridad
2. **No uses múltiples instancias**: Una sola instancia por cuenta
3. **No compartas tu sesión**: El archivo de sesión es personal
4. **Backup de .env**: Guarda una copia segura de tus credenciales
5. **Monitorea logs**: Revisa regularmente los logs para detectar problemas

## 🆘 Qué Hacer si te Banean

Si Telegram bloquea temporalmente tu cuenta:

1. **Espera el tiempo indicado**: No intentes bypass
2. **Reduce el uso**: Cuando se reactive, usa el bot menos frecuentemente
3. **Revisa logs**: Identifica qué causó el ban
4. **Ajusta delays**: Aumenta `min_delay_between_requests` si es necesario

## 📝 Cambios Implementados

### Versión Actual
- ✅ Rate limiting con límite de 20 peticiones/minuto
- ✅ Delay mínimo de 2 segundos entre peticiones
- ✅ Delay de 3 segundos en copia masiva
- ✅ Variables de entorno para tokens
- ✅ Logs detallados de operaciones
- ✅ Manejo robusto de errores
- ✅ Reconexión automática

### Próximas Mejoras
- 🔄 Sistema de queue para peticiones
- 🔄 Persistencia de StringSession en archivo
- 🔄 Dashboard de estadísticas
- 🔄 Alertas de uso excesivo

## 📞 Soporte

Si encuentras problemas de seguridad o bans:
1. Revisa los logs en `logs/bot.log`
2. Verifica que los delays estén funcionando
3. Reduce el límite de peticiones por minuto si es necesario
4. Contacta al administrador con logs relevantes
