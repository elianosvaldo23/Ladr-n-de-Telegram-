"""Lightweight memory and disk monitoring using /proc (no psutil dependency)"""

import logging
import shutil

logger = logging.getLogger(__name__)


def log_memory_usage(context: str = "") -> tuple:
    """Log process memory, system memory, AND disk usage.

    Args:
        context: Optional label included in the log line.

    Returns:
        A tuple ``(rss_mb, system_available_mb, is_critical)``.
        Returns ``(None, None, False)`` on any read error.
    """
    try:
        # Read process memory from /proc/self/status
        rss_mb = 0
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    rss_mb = int(line.split()[1]) / 1024  # KB -> MB
                    break

        # Read system memory from /proc/meminfo
        system_available_mb = 0
        system_total_mb = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    system_total_mb = int(line.split()[1]) / 1024
                elif line.startswith('MemAvailable:'):
                    system_available_mb = int(line.split()[1]) / 1024

        system_used_mb = system_total_mb - system_available_mb
        system_percent = (system_used_mb / system_total_mb * 100) if system_total_mb > 0 else 0

        # Read disk usage
        disk_info = ""
        disk_critical = False
        try:
            from config import TEMP_DOWNLOAD_DIR
            stat = shutil.disk_usage(TEMP_DOWNLOAD_DIR)
            disk_used_mb = stat.used / (1024 * 1024)
            disk_total_mb = stat.total / (1024 * 1024)
            disk_free_mb = stat.free / (1024 * 1024)
            disk_percent = (stat.used / stat.total * 100) if stat.total > 0 else 0
            disk_info = (
                f", Disco({TEMP_DOWNLOAD_DIR})="
                f"{disk_used_mb:.0f}/{disk_total_mb:.0f}MB "
                f"({disk_percent:.0f}%), Libre={disk_free_mb:.0f}MB"
            )
            disk_critical = disk_percent > 90
        except Exception:
            pass

        logger.info(
            f"💾 Memoria {context}: Proceso={rss_mb:.0f}MB, "
            f"Sistema={system_used_mb:.0f}/{system_total_mb:.0f}MB ({system_percent:.0f}%), "
            f"Disponible={system_available_mb:.0f}MB{disk_info}"
        )

        is_critical = system_percent > 85 or disk_critical
        if system_percent > 85:
            logger.error(f"🚨 MEMORIA CRÍTICA: {system_percent:.0f}% usado!")
        if disk_critical:
            logger.error(
                f"🚨 DISCO CRÍTICO: {disk_percent:.0f}% usado en "
                f"{TEMP_DOWNLOAD_DIR}! Solo {disk_free_mb:.0f}MB libres."
            )

        return rss_mb, system_available_mb, is_critical
    except Exception:
        return None, None, False
