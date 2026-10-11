"""
auth.py — clave para las operaciones que ESCRIBEN en la base.

Antes cualquiera podía crear vectores, cambiar puntajes (y con eso la
clasificación) o cargar evidencia desde internet. Ahora esas rutas piden el
header X-Robot-Token con el valor de la variable ROBOT_TOKEN (Railway). Si la
variable no está configurada, las escrituras quedan deshabilitadas (503).
Las lecturas siguen siendo públicas.
"""
import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException


def requiere_token(x_robot_token: Optional[str] = Header(None)) -> None:
    esperado = os.getenv("ROBOT_TOKEN", "")
    if not esperado:
        raise HTTPException(503, "Escritura deshabilitada: falta configurar ROBOT_TOKEN")
    if not x_robot_token or not hmac.compare_digest(x_robot_token, esperado):
        raise HTTPException(401, "Falta o es incorrecto el header X-Robot-Token")
