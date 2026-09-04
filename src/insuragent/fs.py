"""Utilidades de sistema de archivos con permisos restrictivos.

Todo archivo que el sistema crea con datos de asegurados —base transaccional,
trazas, evidencia de siniestros— nace legible sólo por su dueño. El umask por
defecto de la mayoría de las distribuciones crea archivos `644`, es decir
legibles por cualquier usuario de la máquina; ajustarlos a mano no sirve porque
el código los vuelve a crear en cada `make seed`.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

PERMISOS_ARCHIVO = stat.S_IRUSR | stat.S_IWUSR  # 0600
PERMISOS_DIRECTORIO = stat.S_IRWXU  # 0700


def restringir(ruta: Path) -> Path:
    """Deja la ruta accesible sólo para su propietario.

    No es fatal si falla: en un contenedor de sólo lectura o un sistema de
    archivos que no soporta permisos POSIX, el dato sigue siendo válido y el
    servicio debe seguir funcionando.
    """
    try:
        if ruta.exists():
            os.chmod(ruta, PERMISOS_DIRECTORIO if ruta.is_dir() else PERMISOS_ARCHIVO)
    except OSError:
        _LOGGER.debug("No se pudieron restringir los permisos de %s", ruta, exc_info=True)
    return ruta
