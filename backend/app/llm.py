"""Proveedores de modelo de lenguaje.

El resto del motor solo conoce esta interfaz:

    proveedor.generar(mensajes, esquema) -> str (JSON)
    proveedor.local -> True si los datos nunca salen del equipo

Asi se puede cambiar de proveedor sin tocar la logica de negocio (riesgo
"dependencia de un proveedor externo" del PRD).

Politica de datos (PRD, seccion "Politica de uso de IA"):
  - ollama: local. Unico proveedor permitido con datos reales de empleados.
  - groq:   nube, gratuito y rapido. SOLO con datos sinteticos: se niega a
            arrancar si MODO_DATOS no es "sinteticos".

Se usan las APIs REST directamente (libreria estandar, sin dependencias extra).
"""
import copy
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from app.database import RAIZ

load_dotenv(RAIZ / ".env")

MODOS_DATOS = ("reales", "sinteticos")


class ProveedorNoDisponible(Exception):
    """El modelo no responde o rechazo la peticion."""


class ConfiguracionIA(Exception):
    """La configuracion de la IA en el .env no es valida o no es segura."""


def modo_datos() -> str:
    """'reales' (por defecto, lo mas seguro) o 'sinteticos'."""
    modo = os.getenv("MODO_DATOS", "reales").lower()
    if modo not in MODOS_DATOS:
        raise ConfiguracionIA(f"MODO_DATOS='{modo}' no es valido. Opciones: {', '.join(MODOS_DATOS)}")
    return modo


def _post_json(url: str, cuerpo: dict, timeout: float, encabezados: dict | None = None) -> dict:
    peticion = urllib.request.Request(
        url,
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json", **(encabezados or {})},
        method="POST",
    )
    with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


class OllamaProveedor:
    nombre = "ollama"
    local = True

    def __init__(self, modelo=None, url=None, timeout=None, pensar=None, num_ctx=None):
        self.modelo = modelo or os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        # En CPU un reporte tarda minutos y se genera en segundo plano: un
        # timeout corto solo convertia respuestas lentas en fallos.
        self.timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT", "900"))
        # El prompt mide ~2,000 tokens; un reintento suma la respuesta anterior
        # (~900) y los errores, mas la nueva respuesta. 4096 se quedaba corto y
        # Ollama recortaba en silencio el inicio de la conversacion.
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        # Qwen3 y otros modelos "razonadores" piensan antes de responder por
        # defecto, lo que puede sumar minutos sin aportar nada a esta tarea
        # (ya redacta a partir de hechos ya calculados, y nuestro propio ciclo
        # de reintento corrige errores). Lo desactivamos salvo que se pida.
        if pensar is None:
            pensar = os.getenv("OLLAMA_THINK", "false").lower() in ("1", "true", "si", "yes")
        self.pensar = pensar
        # el texto "/no_think" es una convencion propia de la familia Qwen: en
        # otros modelos (Llama, Phi, Gemma...) no significa nada especial y el
        # modelo lo trata como parte del contenido a responder, lo cual puede
        # confundirlo. Solo lo agregamos si el modelo es un Qwen.
        self.entiende_no_think = "qwen" in self.modelo.lower()

    def generar(self, mensajes: list[dict], esquema: dict) -> str:
        if not self.pensar and self.entiende_no_think:
            # "/no_think" en el ultimo mensaje es el metodo mas confiable para
            # Qwen3 entre versiones de Ollama; el parametro "think" de la API
            # ha tenido fallos reportados, sobre todo combinado con "format".
            mensajes = [*mensajes[:-1], {**mensajes[-1], "content": mensajes[-1]["content"] + "\n/no_think"}]
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "stream": False,
            "think": self.pensar,
            "format": esquema,  # salida estructurada: el modelo debe ajustarse a este JSON schema
            "options": {"temperature": 0.2, "num_ctx": self.num_ctx},
        }
        try:
            datos = _post_json(f"{self.url}/api/chat", cuerpo, self.timeout)
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


def esquema_estricto(esquema: dict) -> dict:
    """Copia del esquema apta para el modo estricto de Groq/OpenAI: todo
    objeto lleva additionalProperties=false y todas sus propiedades requeridas."""
    copia = copy.deepcopy(esquema)

    def _ajustar(nodo):
        if isinstance(nodo, dict):
            if nodo.get("type") == "object" and "properties" in nodo:
                nodo["additionalProperties"] = False
                nodo["required"] = list(nodo["properties"])
            for valor in nodo.values():
                _ajustar(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                _ajustar(valor)

    _ajustar(copia)
    return copia


class GroqProveedor:
    """Groq (nube, nivel gratuito sin tarjeta). Solo para datos sinteticos.

    Groq no entrena con los datos por contrato y no los retiene por defecto;
    aun asi los servidores estan fuera de Mexico y la cuenta gratuita no
    incluye contrato de tratamiento de datos (LFPDPPP), por eso el candado.
    """

    nombre = "groq"
    local = False
    URL = "https://api.groq.com/openai/v1/chat/completions"
    REINTENTOS_429 = 3
    ESPERA_MAXIMA_429 = 60

    def __init__(self, modelo=None, url=None, timeout=None, api_key=None, estricto=None, dormir=time.sleep):
        if modo_datos() != "sinteticos":
            raise ConfiguracionIA(
                "Groq envia los datos a servidores externos: solo se permite con datos "
                "sinteticos. Usa LLM_PROVEEDOR=ollama, o pon MODO_DATOS=sinteticos en el "
                ".env si de verdad son datos de prueba."
            )
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ConfiguracionIA("Falta GROQ_API_KEY en el .env (se crea gratis en console.groq.com/keys)")
        self.modelo = modelo or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.url = url or os.getenv("GROQ_URL", self.URL)
        self.timeout = timeout or float(os.getenv("GROQ_TIMEOUT", "120"))
        if estricto is None:
            estricto = os.getenv("GROQ_STRICT", "true").lower() in ("1", "true", "si", "yes")
        self.estricto = estricto
        self.pensar = False
        self._dormir = dormir

    def _cuerpo(self, mensajes: list[dict], esquema: dict) -> dict:
        cuerpo = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "narrativa",
                    "strict": self.estricto,
                    "schema": esquema_estricto(esquema) if self.estricto else esquema,
                },
            },
        }
        # Razonar poco o nada: los hechos ya vienen calculados y los
        # guardarrailes corrigen; razonar solo gasta tokens del limite gratuito.
        if "gpt-oss" in self.modelo:
            cuerpo.update(reasoning_effort="low", include_reasoning=False)
        elif "qwen" in self.modelo:
            cuerpo.update(reasoning_effort="none")
        return cuerpo

    def generar(self, mensajes: list[dict], esquema: dict) -> str:
        cuerpo = self._cuerpo(mensajes, esquema)
        encabezados = {"Authorization": f"Bearer {self.api_key}"}
        for intento in range(self.REINTENTOS_429 + 1):
            try:
                datos = _post_json(self.url, cuerpo, self.timeout, encabezados)
                break
            except urllib.error.HTTPError as exc:
                detalle = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code == 429 and intento < self.REINTENTOS_429:
                    # limite por minuto del plan gratuito: esperar lo que pide Groq
                    espera = float(exc.headers.get("retry-after") or 10)
                    self._dormir(min(espera, self.ESPERA_MAXIMA_429))
                    continue
                pista = {
                    401: " (revisa GROQ_API_KEY)",
                    404: f" (el modelo '{self.modelo}' no existe en Groq; revisa GROQ_MODEL)",
                    429: " (se agoto el limite gratuito; espera o prueba manana)",
                }.get(exc.code, "")
                if exc.code == 400 and self.estricto and "schema" in detalle.lower():
                    pista = " (si el modelo no admite modo estricto, pon GROQ_STRICT=false)"
                raise ProveedorNoDisponible(f"Groq respondio HTTP {exc.code}: {detalle}{pista}") from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                raise ProveedorNoDisponible(f"No se pudo conectar con Groq ({exc}). Revisa tu conexion.") from exc
        try:
            return datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProveedorNoDisponible("Respuesta inesperada de Groq") from exc


PROVEEDORES = {"ollama": OllamaProveedor, "groq": GroqProveedor}


def obtener_proveedor():
    """Proveedor configurado en .env (LLM_PROVEEDOR=ollama | groq).

    La narrativa siempre la redacta un modelo: no hay opcion "sin IA".
    Lanza ConfiguracionIA si el .env no es valido o no es seguro.
    """
    nombre = os.getenv("LLM_PROVEEDOR", "ollama").lower()
    if nombre not in PROVEEDORES:
        raise ConfiguracionIA(
            f"LLM_PROVEEDOR='{nombre}' no es valido. Opciones: {', '.join(PROVEEDORES)}"
        )
    return PROVEEDORES[nombre]()
