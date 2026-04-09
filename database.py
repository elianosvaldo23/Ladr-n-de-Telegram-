"""
Módulo de gestión de base de datos MongoDB
"""

import logging
from typing import Optional, Dict, Any, List
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
import time as _time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MongoDB:
    """Manages the MongoDB connection and all database operations.

    Attributes:
        uri: MongoDB connection URI.
        client: The ``pymongo.MongoClient`` instance (or ``None``).
        db: The selected ``telegram_bot`` database handle (or ``None``).
        is_connected: Whether the last connection attempt succeeded.
    """

    def __init__(self, uri: str):
        """
        Inicializar conexión con MongoDB
        
        Args:
            uri: URI de conexión a MongoDB
        """
        self.uri = uri
        self.client = None
        self.db = None
        self.is_connected = False
        self._last_reconnect_attempt = 0.0  # timestamp of last reconnect try
        self._reconnect_cooldown = 30.0     # seconds to wait between reconnect attempts
        self._connect()
    
    def _connect(self):
        """Establecer conexión con MongoDB (no fatal – el bot puede arrancar sin DB)"""
        try:
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
            )
            # Test connection
            self.client.admin.command('ping')
            
            # Seleccionar base de datos
            self.db = self.client['telegram_bot']
            self.is_connected = True
            
            logger.info("✅ Conexión exitosa con MongoDB")
            
            # Crear índices
            self._create_indexes()
            
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            logger.error(f"❌ Error conectando a MongoDB: {e}")
            self.is_connected = False
            # NO re-lanzamos: el bot puede arrancar sin DB y reconectar después

    def _ensure_connected(self) -> bool:
        """Return True when the DB connection is alive, attempting a reconnect
        (with cooldown) if it was lost."""
        if self.is_connected and self.db is not None:
            return True
        now = _time.monotonic()
        if now - self._last_reconnect_attempt < self._reconnect_cooldown:
            # Todavía en periodo de cooldown; no bloquear
            return False
        self._last_reconnect_attempt = now
        logger.warning("⚠️ MongoDB no conectado – intentando reconectar...")
        self._connect()
        if not self.is_connected:
            logger.error("❌ No se pudo reconectar a MongoDB")
        return self.is_connected
    
    def _create_indexes(self):
        """Crear índices para optimizar consultas"""
        try:
            # Índice para usuarios
            self.db.users.create_index("user_id", unique=True)
            
            # Índice para configuración
            self.db.config.create_index("key", unique=True)
            
            # Índice para configuración de usuarios
            self.db.user_configs.create_index("user_id", unique=True)
            
            logger.info("✅ Índices creados correctamente")
        except Exception as e:
            logger.warning(f"⚠️ Error creando índices: {e}")
    
    def close(self):
        """Cerrar conexión con MongoDB"""
        if self.client:
            self.client.close()
            logger.info("Conexión con MongoDB cerrada")
    
    # ============== GESTIÓN DE USUARIOS ==============
    
    def save_user(self, user_data: Dict[str, Any]) -> bool:
        """Upsert a user document.

        Args:
            user_data: Must contain ``user_id``; other keys are optional
                (``username``, ``first_name``, ``last_name``, ``is_premium``, ...).

        Returns:
            True on success, False on error or missing ``user_id``.
        """
        if not self._ensure_connected():
            return False
        try:
            user_id = user_data.get('user_id')
            if not user_id:
                logger.error("user_id es requerido")
                return False
            
            # Agregar timestamp
            user_data['updated_at'] = datetime.utcnow()
            
            # Upsert (actualizar si existe, crear si no)
            result = self.db.users.update_one(
                {'user_id': user_id},
                {'$set': user_data, '$setOnInsert': {'created_at': datetime.utcnow()}},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(f"Usuario {user_id} guardado/actualizado correctamente")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error guardando usuario: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single user document by Telegram user ID."""
        if not self._ensure_connected():
            return None
        try:
            user = self.db.users.find_one({'user_id': user_id})
            return user
        except Exception as e:
            logger.error(f"Error obteniendo usuario {user_id}: {e}")
            return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Return all user documents."""
        if not self._ensure_connected():
            return []
        try:
            users = list(self.db.users.find({}))
            return users
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return []
    
    def get_premium_users(self) -> List[int]:
        """Return a list of user IDs with active premium."""
        if not self._ensure_connected():
            return []
        try:
            users = self.db.users.find({'is_premium': True})
            return [user['user_id'] for user in users]
        except Exception as e:
            logger.error(f"Error obteniendo usuarios premium: {e}")
            return []
    
    def set_user_premium(self, user_id: int, is_premium: bool = True, days: int = 30) -> bool:
        """Activate or deactivate premium for a user.

        Args:
            user_id: Telegram user ID.
            is_premium: ``True`` to activate, ``False`` to deactivate.
            days: Number of premium days (only used when activating).

        Returns:
            True if the document was modified.
        """
        if not self._ensure_connected():
            return False
        try:
            update_data = {
                'is_premium': is_premium,
                'premium_updated_at': datetime.utcnow()
            }
            
            if is_premium:
                # Calcular fecha de expiración
                expiry_date = datetime.utcnow() + timedelta(days=days)
                update_data['premium_expiry_date'] = expiry_date
                update_data['premium_days_granted'] = days
                update_data['premium_start_date'] = datetime.utcnow()
                update_data['premium_notified'] = False
            else:
                # Al desactivar premium, limpiar campos
                update_data['premium_expiry_date'] = None
                update_data['premium_days_granted'] = None
                update_data['premium_start_date'] = None
                update_data['premium_notified'] = False
            
            result = self.db.users.update_one(
                {'user_id': user_id},
                {'$set': update_data}
            )
            
            if result.modified_count > 0:
                logger.info(f"Premium {'activado' if is_premium else 'desactivado'} para usuario {user_id}{f' por {days} días' if is_premium else ''}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error actualizando premium del usuario {user_id}: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """
        Eliminar un usuario
        
        Args:
            user_id: ID del usuario
        
        Returns:
            bool: True si se eliminó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.users.delete_one({'user_id': user_id})
            if result.deleted_count > 0:
                logger.debug(f"Usuario {user_id} eliminado")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando usuario {user_id}: {e}")
            return False
    
    # ============== GESTIÓN DE CONFIGURACIÓN ==============
    
    def save_config(self, key: str, value: Any) -> bool:
        """
        Guardar configuración
        
        Args:
            key: Clave de configuración
            value: Valor de configuración
        
        Returns:
            bool: True si se guardó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.config.update_one(
                {'key': key},
                {
                    '$set': {
                        'value': value,
                        'updated_at': datetime.utcnow()
                    },
                    '$setOnInsert': {'created_at': datetime.utcnow()}
                },
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(f"Configuración '{key}' guardada correctamente")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error guardando configuración '{key}': {e}")
            return False
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Obtener configuración
        
        Args:
            key: Clave de configuración
            default: Valor por defecto si no existe
        
        Returns:
            Valor de configuración o default
        """
        if not self._ensure_connected():
            return default
        try:
            config = self.db.config.find_one({'key': key})
            if config:
                return config.get('value', default)
            return default
        except Exception as e:
            logger.error(f"Error obteniendo configuración '{key}': {e}")
            return default
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        Obtener toda la configuración
        
        Returns:
            Diccionario con todas las configuraciones
        """
        if not self._ensure_connected():
            return {}
        try:
            configs = self.db.config.find({})
            return {config['key']: config['value'] for config in configs}
        except Exception as e:
            logger.error(f"Error obteniendo configuración: {e}")
            return {}
    
    def delete_config(self, key: str) -> bool:
        """
        Eliminar configuración
        
        Args:
            key: Clave de configuración
        
        Returns:
            bool: True si se eliminó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.config.delete_one({'key': key})
            if result.deleted_count > 0:
                logger.debug(f"Configuración '{key}' eliminada")
                return True
            return False
        except Exception as e:
            logger.error(f"Error eliminando configuración '{key}': {e}")
            return False
    
    # ============== GESTIÓN DE USERBOT CONFIG ==============
    
    def save_userbot_config(self, config_data: Dict[str, Any]) -> bool:
        """
        Guardar configuración completa del userbot
        
        Args:
            config_data: Diccionario con configuración del userbot
        
        Returns:
            bool: True si se guardó correctamente
        """
        return self.save_config('userbot_config', config_data)
    
    def get_userbot_config(self) -> Dict[str, Any]:
        """
        Obtener configuración del userbot
        
        Returns:
            Diccionario con configuración del userbot
        """
        return self.get_config('userbot_config', {})
    
    def update_userbot_config(self, key: str, value: Any) -> bool:
        """
        Actualizar un valor específico de la configuración del userbot
        
        Args:
            key: Clave dentro de la configuración
            value: Valor a actualizar
        
        Returns:
            bool: True si se actualizó correctamente
        """
        try:
            current_config = self.get_userbot_config()
            current_config[key] = value
            return self.save_userbot_config(current_config)
        except Exception as e:
            logger.error(f"Error actualizando configuración del userbot: {e}")
            return False
    
    # ============== GESTIÓN DE CONFIGURACIÓN DE USUARIOS ==============
    
    def save_user_config(self, user_id: int, config_data: Dict[str, Any]) -> bool:
        """
        Guardar configuración de un usuario específico
        
        Args:
            user_id: ID del usuario
            config_data: Diccionario con configuración del usuario
        
        Returns:
            bool: True si se guardó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            # CORRECCIÓN CRÍTICA: Remover campo _id de MongoDB para evitar error
            # "Performing an update on the path '_id' would modify the immutable field '_id'"
            config_to_save = {k: v for k, v in config_data.items() if k != '_id'}
            config_to_save['user_id'] = user_id
            config_to_save['updated_at'] = datetime.utcnow()
            
            result = self.db.user_configs.update_one(
                {'user_id': user_id},
                {
                    '$set': config_to_save,
                    '$setOnInsert': {'created_at': datetime.utcnow()}
                },
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(f"Configuración del usuario {user_id} guardada correctamente")
                return True
            
            # matched_count > 0 pero modified_count == 0 significa que el doc existe pero no cambió
            logger.debug(f"Configuración del usuario {user_id} sin cambios (ya era igual)")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando configuración del usuario {user_id}: {e}")
            return False
    
    def get_user_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtener configuración de un usuario específico
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Diccionario con configuración del usuario o None si no existe
        """
        if not self._ensure_connected():
            return None
        try:
            config = self.db.user_configs.find_one({'user_id': user_id})
            if config:
                # Remover _id de MongoDB para evitar problemas al guardar
                config.pop('_id', None)
                return config
            
            # Retornar configuración por defecto
            return {
                'user_id': user_id,
                'target_channel': None,
                'filters': {
                    'videos': True,
                    'photos': True,
                    'documents': True,
                    'audio': True,
                    'text': True,
                    'stickers': True
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo configuración del usuario {user_id}: {e}")
            return None
    
    def update_user_target_channel(self, user_id: int, target_channel) -> bool:
        """
        Actualizar directamente el canal destino de un usuario en MongoDB
        Usa $set directo para evitar problemas de lectura-modificación-escritura
        
        Args:
            user_id: ID del usuario
            target_channel: Nuevo canal destino (str o None para eliminar)
        
        Returns:
            bool: True si se actualizó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.user_configs.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'target_channel': target_channel,
                        'updated_at': datetime.utcnow()
                    },
                    '$setOnInsert': {'created_at': datetime.utcnow()}
                },
                upsert=True
            )
            
            logger.debug(f"Canal destino actualizado para usuario {user_id}: {target_channel}")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando canal destino del usuario {user_id}: {e}")
            return False
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Buscar un usuario por su username
        
        Args:
            username: Username del usuario (sin @)
        
        Returns:
            Diccionario con datos del usuario o None si no existe
        """
        if not self._ensure_connected():
            return None
        try:
            user = self.db.users.find_one({'username': username})
            return user
        except Exception as e:
            logger.error(f"Error buscando usuario por username {username}: {e}")
            return None
    
    def update_user_filter(self, user_id: int, filter_type: str, enabled: bool) -> bool:
        """
        Actualizar un filtro específico de un usuario
        
        Args:
            user_id: ID del usuario
            filter_type: Tipo de filtro (videos, photos, documents, etc.)
            enabled: True para activar, False para desactivar
        
        Returns:
            bool: True si se actualizó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.user_configs.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        f'filters.{filter_type}': enabled,
                        'updated_at': datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(f"Filtro '{filter_type}' actualizado para usuario {user_id}")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando filtro del usuario {user_id}: {e}")
            return False
    
    # ============== ESTADÍSTICAS ==============
    
    def get_users_expiring_soon(self, days: int = 3) -> List[Dict[str, Any]]:
        """
        Obtener usuarios cuyo premium expira pronto
        
        Args:
            days: Número de días para considerar "pronto" (default: 3)
        
        Returns:
            Lista de usuarios con premium próximo a expirar
        """
        if not self._ensure_connected():
            return []
        try:
            threshold_date = datetime.utcnow() + timedelta(days=days)
            current_date = datetime.utcnow()
            
            users = self.db.users.find({
                'is_premium': True,
                'premium_expiry_date': {
                    '$gte': current_date,
                    '$lte': threshold_date
                },
                'premium_notified': False
            })
            
            result = []
            for user in users:
                expiry_date = user.get('premium_expiry_date')
                if expiry_date:
                    days_remaining = (expiry_date - current_date).days
                    result.append({
                        'user_id': user['user_id'],
                        'username': user.get('username'),
                        'first_name': user.get('first_name'),
                        'expiry_date': expiry_date,
                        'days_remaining': days_remaining
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Error obteniendo usuarios con premium próximo a expirar: {e}")
            return []
    
    def mark_user_notified(self, user_id: int) -> bool:
        """
        Marcar que se notificó al usuario sobre expiración de premium
        
        Args:
            user_id: ID del usuario
        
        Returns:
            bool: True si se actualizó correctamente
        """
        if not self._ensure_connected():
            return False
        try:
            result = self.db.users.update_one(
                {'user_id': user_id},
                {'$set': {'premium_notified': True}}
            )
            
            if result.modified_count > 0:
                logger.debug(f"Usuario {user_id} marcado como notificado")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error marcando usuario {user_id} como notificado: {e}")
            return False
    
    def check_expired_premium(self) -> List[int]:
        """
        Verificar y desactivar usuarios con premium expirado
        
        Returns:
            Lista de IDs de usuarios cuyo premium fue desactivado
        """
        if not self._ensure_connected():
            return []
        try:
            current_date = datetime.utcnow()
            
            # Encontrar usuarios con premium expirado
            expired_users = self.db.users.find({
                'is_premium': True,
                'premium_expiry_date': {'$lt': current_date}
            })
            
            expired_ids = []
            for user in expired_users:
                user_id = user['user_id']
                # Desactivar premium
                self.set_user_premium(user_id, is_premium=False)
                expired_ids.append(user_id)
                logger.info(f"Premium expirado para usuario {user_id}")
            
            return expired_ids
            
        except Exception as e:
            logger.error(f"Error verificando premium expirado: {e}")
            return []
    
    def get_premium_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtener información detallada del premium de un usuario
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Diccionario con información del premium o None
        """
        if not self._ensure_connected():
            return None
        try:
            user = self.db.users.find_one({'user_id': user_id})
            
            if not user or not user.get('is_premium'):
                return None
            
            expiry_date = user.get('premium_expiry_date')
            if not expiry_date:
                return None
            
            days_remaining = (expiry_date - datetime.utcnow()).days
            
            return {
                'user_id': user_id,
                'username': user.get('username'),
                'first_name': user.get('first_name'),
                'is_premium': True,
                'premium_start_date': user.get('premium_start_date'),
                'premium_expiry_date': expiry_date,
                'premium_days_granted': user.get('premium_days_granted', 0),
                'days_remaining': max(0, days_remaining)
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo información de premium del usuario {user_id}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtener estadísticas generales
        
        Returns:
            Diccionario con estadísticas
        """
        if not self._ensure_connected():
            return {'total_users': 0, 'premium_users': 0, 'free_users': 0}
        try:
            total_users = self.db.users.count_documents({})
            premium_users = self.db.users.count_documents({'is_premium': True})
            
            return {
                'total_users': total_users,
                'premium_users': premium_users,
                'free_users': total_users - premium_users
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {
                'total_users': 0,
                'premium_users': 0,
                'free_users': 0
            }

    # ============== SISTEMA DE PRUEBA GRATUITA ==============

    FREE_TRIAL_USES = 5  # Número de usos gratuitos de prueba

    def get_free_trial_info(self, user_id: int) -> Dict[str, Any]:
        """
        Obtener información de la prueba gratuita del usuario.
        
        Returns:
            Dict con: trial_activated (bool), trial_uses_left (int), 
                      trial_used (bool), channel_joined (bool)
        """
        if not self._ensure_connected():
            return {'trial_activated': False, 'trial_uses_left': 0, 'trial_used': False, 'channel_joined': False}
        try:
            user = self.db.users.find_one({'user_id': user_id})
            if not user:
                return {
                    'trial_activated': False,
                    'trial_uses_left': 0,
                    'trial_used': False,
                    'channel_joined': False
                }
            
            trial_activated = user.get('free_trial_activated', False)
            trial_uses_left = user.get('free_trial_uses_left', 0)
            channel_joined = user.get('free_trial_channel_joined', False)
            trial_used = trial_activated and trial_uses_left == 0
            
            return {
                'trial_activated': trial_activated,
                'trial_uses_left': trial_uses_left,
                'trial_used': trial_used,
                'channel_joined': channel_joined
            }
        except Exception as e:
            logger.error(f"Error obteniendo info de prueba gratuita del usuario {user_id}: {e}")
            return {
                'trial_activated': False,
                'trial_uses_left': 0,
                'trial_used': False,
                'channel_joined': False
            }

    def activate_free_trial(self, user_id: int) -> bool:
        """
        Activar la prueba gratuita premium para el usuario.
        Solo puede activarse una vez por usuario.
        Si el usuario no existe en la BD, se crea automáticamente.
        
        Returns:
            True si se activó, False si ya estaba activado o hubo error
        """
        if not self._ensure_connected():
            return False
        try:
            user = self.db.users.find_one({'user_id': user_id})
            
            if user:
                # Verificar si ya fue activado
                if user.get('free_trial_activated', False):
                    logger.warning(f"Usuario {user_id} ya tiene la prueba gratuita activada")
                    return False
                
                # Actualizar usuario existente
                result = self.db.users.update_one(
                    {'user_id': user_id},
                    {'$set': {
                        'free_trial_activated': True,
                        'free_trial_uses_left': self.FREE_TRIAL_USES,
                        'free_trial_channel_joined': True,
                        'free_trial_activated_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    }}
                )
                
                if result.modified_count > 0:
                    logger.info(f"✅ Prueba gratuita activada para usuario {user_id} ({self.FREE_TRIAL_USES} usos)")
                    return True
                return False
            else:
                # Usuario no existe: crearlo con trial activado usando upsert
                result = self.db.users.update_one(
                    {'user_id': user_id},
                    {'$set': {
                        'user_id': user_id,
                        'free_trial_activated': True,
                        'free_trial_uses_left': self.FREE_TRIAL_USES,
                        'free_trial_channel_joined': True,
                        'free_trial_activated_at': datetime.utcnow(),
                        'is_premium': False,
                        'created_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    }},
                    upsert=True
                )
                if result.upserted_id or result.modified_count > 0:
                    logger.info(f"✅ Usuario {user_id} creado con prueba gratuita ({self.FREE_TRIAL_USES} usos)")
                    return True
                return False
            
        except Exception as e:
            logger.error(f"Error activando prueba gratuita para usuario {user_id}: {e}")
            return False

    def use_free_trial(self, user_id: int) -> bool:
        """
        Consumir un uso de la prueba gratuita.
        
        Returns:
            True si quedaban usos y se consumió uno, False si no quedan usos
        """
        if not self._ensure_connected():
            return False
        try:
            user = self.db.users.find_one({'user_id': user_id})
            if not user:
                return False
            
            uses_left = user.get('free_trial_uses_left', 0)
            if uses_left <= 0:
                return False
            
            result = self.db.users.update_one(
                {'user_id': user_id, 'free_trial_uses_left': {'$gt': 0}},
                {'$inc': {'free_trial_uses_left': -1},
                 '$set': {'updated_at': datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.debug(f"Prueba gratuita usada por usuario {user_id}. Quedan {uses_left - 1} usos.")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error consumiendo uso de prueba gratuita para usuario {user_id}: {e}")
            return False

    def mark_trial_channel_joined(self, user_id: int) -> bool:
        """Marcar que el usuario se unió al canal requerido."""
        if not self._ensure_connected():
            return False
        try:
            result = self.db.users.update_one(
                {'user_id': user_id},
                {'$set': {
                    'free_trial_channel_joined': True,
                    'updated_at': datetime.utcnow()
                }}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error marcando canal unido para usuario {user_id}: {e}")
            return False


# Instancia global de MongoDB (se inicializa en bot.py)
db: Optional[MongoDB] = None

def initialize_database(uri: str) -> 'MongoDB':
    """
    Inicializar base de datos. No lanza excepción aunque MongoDB no esté disponible;
    el bot puede arrancar y reconectará automáticamente en cada operación.
    
    Args:
        uri: URI de conexión a MongoDB
    
    Returns:
        Instancia de MongoDB (puede estar desconectada temporalmente)
    """
    global db
    db = MongoDB(uri)
    if not db.is_connected:
        logger.warning("⚠️ MongoDB no disponible al iniciar; el bot reconectará automáticamente")
    return db

def get_database() -> Optional[MongoDB]:
    """
    Obtener instancia de la base de datos
    
    Returns:
        Instancia de MongoDB o None si no está inicializada
    """
    return db
