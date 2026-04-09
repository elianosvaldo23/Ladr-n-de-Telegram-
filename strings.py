"""Centralized UI strings - eliminates duplicate text across handlers."""

# ============== ERRORS ==============
ERR_PREMIUM_REQUIRED = (
    "⭐ **Función Premium Requerida**\n\n"
    "{feature}\n\n"
    "🎁 **¿Sabías que puedes probar el Premium GRATIS?**\n"
    "Únete a nuestro canal y obtén **{free_uses} extracciones gratuitas**."
)

ERR_USERBOT_NOT_CONFIGURED = (
    "⚠️ **Userbot no configurado**\n\n"
    "El administrador debe configurar el userbot primero.\n"
    "Usa /start para más información."
)

ERR_USERBOT_CONNECT_FAILED = (
    "❌ No se pudo conectar el userbot.\n"
    "Contacta al administrador."
)

ERR_CHANNEL_ACCESS = (
    "❌ **No tienes acceso a este canal privado**\n\n"
    "🔑 **Para acceder:**\n"
    "1️⃣ Envíame el enlace de invitación del canal\n"
    "   (formato: `https://t.me/+hash` o `https://t.me/joinchat/hash`)\n"
    "2️⃣ Me uniré al canal automáticamente\n"
    "3️⃣ Luego envía nuevamente el enlace del contenido"
)

ERR_MESSAGE_ID = (
    "❌ No se pudo extraer el ID del mensaje del enlace.\n\n"
    "Asegúrate de enviar un enlace completo:\n"
    "• `https://t.me/canal/123` - Extraer un mensaje\n"
    "• `https://t.me/canal/123 5` - Extraer 5 mensajes consecutivos"
)

ERR_TIMEOUT = (
    "⏱️ **Error de Conexión**\n\n"
    "El servidor no responde. Esto puede ocurrir si:\n"
    "• Hay problemas temporales de red\n"
    "• El servidor está sobrecargado\n\n"
    "Por favor, intenta nuevamente en unos momentos."
)

ERR_CHAT_NOT_FOUND = (
    "❌ **No se puede acceder al canal**\n\n"
    "Posibles razones:\n"
    "• El canal es privado y no tienes acceso\n"
    "• El canal fue eliminado\n"
    "• El enlace es inválido\n\n"
    "Para canales privados, envía primero el enlace de invitación."
)

# ============== FREE TRIAL ==============
TRIAL_USING = "🎁 **Usando tu Prueba Gratuita** ({uses_left} usos restantes)"

TRIAL_USED = "🎁 *Prueba gratuita utilizada.* Te quedan **{uses_left}** uso(s) más."

TRIAL_EXHAUSTED = "⚠️ *Has agotado tu prueba gratuita.* Considera obtener Premium para continuar."

# ============== INVITE LINK RESULTS ==============
INVITE_JOINED = (
    "✅ ¡Me he unido exitosamente al canal!\n\n"
    "Ahora envíame el enlace del contenido que deseas extraer.\n\n"
    "📌 **Ejemplos:**\n"
    "• `https://t.me/c/1234567890/123` - Extraer un mensaje\n"
    "• `https://t.me/c/1234567890/123 5` - Extraer 5 mensajes desde el 123"
)

INVITE_ALREADY_MEMBER = (
    "ℹ️ Ya estoy unido a este canal.\n\n"
    "Ahora envíame el enlace del contenido que deseas extraer.\n\n"
    "📌 **Ejemplos:**\n"
    "• `https://t.me/c/1234567890/123` - Extraer un mensaje\n"
    "• `https://t.me/c/1234567890/123 5` - Extraer 5 mensajes desde el 123"
)

INVITE_PENDING = (
    "⏳ **Solicitud de unión enviada**\n\n"
    "✅ Se ha enviado exitosamente la solicitud para unirse a este canal/grupo.\n\n"
    "🔔 **El administrador debe aceptar la solicitud primero**\n\n"
    "📌 **Qué hacer ahora:**\n"
    "1️⃣ Espera a que el administrador del canal acepte la solicitud\n"
    "2️⃣ Una vez aceptada, envía el enlace de invitación nuevamente\n"
    "3️⃣ Luego podrás enviar el enlace del contenido a extraer\n\n"
    "💡 **Tip:** Puedes contactar al administrador del canal para acelerar la aprobación."
)

INVITE_EXPIRED = (
    "❌ **El enlace de invitación ha expirado**\n\n"
    "🔄 **Qué hacer:**\n"
    "1️⃣ Solicita al administrador del canal un nuevo enlace de invitación\n"
    "2️⃣ Asegúrate de que el enlace no tenga límite de usos o tiempo\n"
    "3️⃣ Envía el nuevo enlace aquí para unirme al canal\n\n"
    "💡 **Nota:** Los enlaces de invitación pueden tener fecha de expiración o límite de usos."
)

INVITE_INVALID = (
    "❌ **Enlace de invitación inválido**\n\n"
    "🔍 **Verifica que el enlace:**\n"
    "• Esté completo y sin errores\n"
    "• Tenga el formato correcto: `https://t.me/+ABC123...` o `https://t.me/joinchat/ABC123...`\n"
    "• No esté corrupto o modificado\n\n"
    "💡 **Solución:** Solicita un nuevo enlace de invitación al administrador del canal."
)

# ============== FILTERS ==============
FILTER_NAMES = {
    'videos': '🎥 Videos',
    'photos': '📸 Fotos',
    'documents': '📎 Documentos',
    'audio': '🎵 Audio',
    'text': '📝 Texto',
    'stickers': '🎭 Stickers'
}

FILTER_LABELS = {
    'videos': 'Videos',
    'photos': 'Fotos',
    'documents': 'Documentos',
    'audio': 'Audio',
    'text': 'Texto',
    'stickers': 'Stickers'
}

# ============== FLOOD WAIT ==============
FLOODWAIT_EXPLANATION = (
    "⏳ **Pausa de Telegram (FloodWait)**\n\n"
    "Los mensajes de tipo *\"Waiting for X seconds before continuing "
    "(required by upload.SaveBigFilePart)\"* son **normales**.\n\n"
    "🔒 **¿Qué significan?**\n"
    "Telegram limita la velocidad de subida/descarga de archivos grandes "
    "para balancear la carga de sus servidores.  Pyrogram espera "
    "automáticamente el tiempo indicado y reintenta.\n\n"
    "✅ **¿Afecta a la cuenta?**\n"
    "No.  Es un mecanismo estándar de rate-limiting.  Mientras el bot "
    "respete las pausas (y lo hace), **no hay riesgo de ban**.\n\n"
    "💡 Solo se pausa el servicio si se acumulan demasiados FloodWaits "
    "consecutivos en poco tiempo (protección anti-ban integrada)."
)

# ============== MISC ==============
CANCEL_SUCCESS = (
    "🛑 **Operación Cancelada**\n\n"
    "La descarga/subida ha sido detenida correctamente."
)

BACK_TO_MENU_BTN = "🔙 Menú Principal"
BACK_BTN = "🔙 Volver"
CANCEL_BTN = "❌ Cancelar"
