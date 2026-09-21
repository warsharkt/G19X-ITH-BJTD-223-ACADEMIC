"""Proveedores de modelo de lenguaje.

El resto del motor solo conoce esta interfaz:

    proveedor.generar(mensajes, esquema) -> str (JSON)

Asi se puede cambiar Ollama por Gemini, Groq u otro sin tocar la logica de
negocio (riesgo "dependencia de un proveedor externo", seccion 12 del PRD).

Se usa la API REST de Ollama directamente (libreria estandar, sin
dependencias extra). Los datos de RRHH nunca salen del equipo.
"""
import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

from app.database import RAIZ

load_dotenv(RAIZ / ".env")


class ProveedorNoDisponible(Exception):
    """El modelo no responde o rechazo la peticion."""


class OllamaProveedor:
    nombre = "ollama"

    def __init__(self, modelo=None, url=None, timeout=None):
        self.modelo = modelo or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        # un modelo local en CPU puede tardar minutos en responder
        self.timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT", "300"))

    def generar(self, mensajes: list[dict], esquema: dict) -> str:
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "stream": False,
            "format": esquema,  # salida estructurada: el modelo debe ajustarse a este JSON schema
            "options": {"temperature": 0.2, "num_ctx": 4096},
        }
        peticion = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", errors="replace")[:300]
            pista = f" (descarga el modelo con: ollama pull {self.modelo})" if exc.code == 404 else ""
            raise ProveedorNoDisponible(f"Ollama respondio HTTP {exc.code}: {detalle}{pista}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ProveedorNoDisponible(
                f"No se pudo conectar con Ollama en {self.url} ({exc}). "
                "Verifica que Ollama este abierto."
            ) from exc
        try:
            return datos["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise ProveedorNoDisponible("Respuesta inesperada de Ollama") from exc


def obtener_proveedor():
    """Proveedor configurado en .env (LLM_PROVEEDOR=ollama | ninguno).

    Devuelve None si la IA esta desactivada: el motor usa entonces las
    plantillas deterministas.
    """
    nombre = os.getenv("LLM_PROVEEDOR", "ollama").lower()
    if nombre == "ollama":
        return OllamaProveedor()
    return None
