"""Servicio integrador de TiendaIA (Laboratorio 1).
Combina varios servicios en la nube a través de sus APIs públicas:
- Open-Meteo (REST, sin llave): geocodificación y clima actual.
- Countries (GraphQL, sin llave): datos de un país.
- Supabase (base de datos como servicio, REST con llave): historial de consultas.
Es opcional; sin llave el historial vive en memoria y se pierde (pruébelo en Vercel).
"""
import os
import time
import requests # cliente HTTP para llamar a las APIs externas
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- Configuración
# Las URL se leen de variables de entorno para poder cambiarlas sin tocar el
# código (por ejemplo, apuntar a un servidor de pruebas).
GEOCODING_URL = os.getenv("GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search")
CLIMA_URL = os.getenv("CLIMA_URL", "https://api.open-meteo.com/v1/forecast")
PAISES_URL = os.getenv("PAISES_URL", "https://countries.trevorblades.com/")
# https://<proyecto>.supabase.co ; rstrip("/") evita una doble barra al armar URL
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
# Llave secreta: nunca se escribe en el código, solo vive en el servidor
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI(title="TiendaIA - Servicio integrador")

# Timeout (conexión, lectura) en segundos: 3 s para conectar y 10 s para recibir
# la respuesta. Nunca se espera para siempre a un servicio externo.
TIEMPO_ESPERA = (3, 10)
sesion = requests.Session() # reutiliza conexiones TCP entre peticiones (más rápido)

# Caché en memoria: clave -> (valor, instante en que expira)
_cache: dict[str, tuple[object, float]] = {}

# Códigos meteorológicos WMO que devuelve Open-Meteo, traducidos a texto
CODIGOS_WMO = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado",
    3: "nublado", 45: "niebla", 51: "llovizna", 61: "lluvia ligera",
    63: "lluvia", 65: "lluvia fuerte", 80: "chubascos", 95: "tormenta"
}

# ---------------------------------------------------------------- Llamadas externas
def llamar(metodo: str, url: str, **kwargs) -> dict:
    """Llama a una API externa y devuelve su JSON.
    Recibe el método HTTP, la URL y los argumentos de requests (params, json,
    headers). Hace un reintento si falla la red o el servidor responde 5xx.
    Traduce los fallos a códigos HTTP propios: 503 si el proveedor limita el uso
    (429), 504 si no responde a tiempo y 502 si responde mal o no se puede conectar.
    """
    for intento in (1, 2):
        try:
            r = sesion.request(metodo, url, timeout=TIEMPO_ESPERA, **kwargs)
            # Un 5xx suele ser una falla pasajera del proveedor: se reintenta una vez
            if r.status_code >= 500 and intento == 1:
                time.sleep(0.5) # espera breve y reintenta
                continue
            # 429 = "demasiadas peticiones": el plan gratuito tiene un límite de uso.
            # Se responde 503 (servicio no disponible por ahora), no es culpa del cliente.
            if r.status_code == 429:
                raise HTTPException(
                    503, "Límite de uso del proveedor alcanzado; intente más tarde"
                )
            r.raise_for_status() # 4xx (o 5xx en el 2o intento) lanza HTTPError
            return r.json()
        except requests.Timeout:
            # 504 Gateway Timeout: el servicio de atrás no contestó a tiempo
            if intento == 2:
                raise HTTPException(504, f"{url} no respondió a tiempo")
        except requests.HTTPError as e:
            # 502 Bad Gateway: el proveedor respondió, pero con un error
            raise HTTPException(502, f"{url} respondió {e.response.status_code}")
        except requests.JSONDecodeError:
            # La respuesta no es JSON válido: no es una falla de red, no se reintenta
            raise
        except requests.RequestException:
            # Falla de red (DNS, conexión rechazada...): se reintenta una vez y luego 502
            if intento == 2:
                raise HTTPException(502, f"No fue posible conectar con {url}")

    raise HTTPException(502, f"{url} falló después de 2 intentos")


def con_cache(clave: str, segundos: int, obtener):
    """Guarda respuestas un tiempo (TTL) para no repetir llamadas idénticas.
    Devuelve (valor, True) si salió de la caché o (valor, False) si se llamó
    a obtener() porque no había valor o ya había expirado.
    """
    valor, expira = _cache.get(clave, (None, 0.0))
    if time.time() < expira: # todavía vigente: no se llama a la API
        return valor, True
    valor = obtener()
    _cache[clave] = (valor, time.time() + segundos)
    return valor, False


# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Verificación de salud: responde 200 e indica dónde se guarda el historial."""
    return {"servicio": "integrador", "status": "ok", "historial": ALMACEN}


@app.get("/clima")
def clima(ciudad: str = Query("Ciudad Valles", min_length=2, max_length=80)):
    """Clima actual de una ciudad usando dos llamadas REST a Open-Meteo.
    Responde 200 con el clima, 404 si la ciudad no existe, 422 si el nombre es
    muy corto o muy largo (lo valida Query) y 502/503/504 si falla Open-Meteo.
    """
    t0 = time.perf_counter()

    def obtener():
        # 1) Geocodificación: nombre de la ciudad -> latitud y longitud
        geo = llamar("GET", GEOCODING_URL, params={"name": ciudad, "count": 1, "language": "es"})

        if not geo.get("results"):
            raise HTTPException(404, f"No se encontró la ciudad '{ciudad}'")
        lugar = geo["results"][0]
        # 2) Pronóstico: con las coordenadas se piden solo las variables necesarias
        datos = llamar("GET", CLIMA_URL, params={
            "latitude": lugar["latitude"], "longitude": lugar["longitude"],
            "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code",
            "timezone": "auto"
        })
        actual = datos["current"]
        # Se arma una respuesta propia, con nombres en español y solo lo útil
        return {
            "ciudad": lugar["name"], "pais": lugar.get("country"),
            "temperatura_c": actual["temperature_2m"],
            "humedad_pct": actual["relative_humidity_2m"],
            "precipitacion_mm": actual["precipitation"],
            "descripcion": CODIGOS_WMO.get(actual["weather_code"], "otro"),
            "hora_local": actual["time"]
        }

    # El clima cambia poco en 10 minutos: se guarda 600 s en caché
    datos, de_cache = con_cache(f"clima:{ciudad.lower()}", 600, obtener)
    return {
        **datos, "desde_cache": de_cache,
        "latencia_ms": round((time.perf_counter() - t0) * 1000, 1)
    }


# Consulta GraphQL: el cliente pide exactamente los campos que necesita.
# $codigo es una variable; ID! significa "identificador obligatorio".
CONSULTA_PAIS = """
query ($codigo: ID!) {
  country(code: $codigo) {
    name native capital currency
    languages { name } continent { name }
  }
}"""


@app.get("/paises/{codigo}")
def pais(codigo: str):
    """Datos de un país por su código ISO de 2 letras (API GraphQL de Countries).
    Responde 200 con los datos, 422 si el código no tiene 2 letras, 404 si el
    país no existe y 502/503/504 si falla el proveedor.
    """
    # 422 Unprocessable Entity: la petición llegó bien, pero el dato no es válido
    if len(codigo) != 2 or not codigo.isalpha():
        raise HTTPException(422, "Use el código ISO de 2 letras, p. ej. MX")
    t0 = time.perf_counter()
    # GraphQL siempre usa POST a una sola URL; la consulta va en el cuerpo JSON.
    # Los datos de un país casi no cambian: caché de 86400 s (un día).
    resp, de_cache = con_cache(
        f"pais:{codigo.upper()}", 86400, lambda: llamar(
            "POST", PAISES_URL,
            json={"query": CONSULTA_PAIS, "variables": {"codigo": codigo.upper()}}
        )
    )
    # GraphQL responde 200 aun con errores: hay que revisar "errors" y "data"
    if resp.get("errors") or not resp.get("data", {}).get("country"):
        raise HTTPException(404, "País no encontrado")
    p = resp["data"]["country"]
    return {
        "nombre": p["name"], "nombre_nativo": p["native"], "capital": p["capital"],
        "moneda": p["currency"], "idiomas": [i["name"] for i in p["languages"]],
        "continente": p["continent"]["name"], "desde_cache": de_cache,
        "latencia_ms": round((time.perf_counter() - t0) * 1000, 1)
    }


class SolicitudRecomendacion(BaseModel):
    """Cuerpo JSON de POST /recomendacion; Pydantic responde 422 si no es válido."""
    ciudad: str = Field("Ciudad Valles", min_length=2, max_length=80)
    # Lista de 1 a 10 productos; si no se envía, se usan productos de la Huasteca
    productos: list[str] = Field(
        default=["Café de la Huasteca", "Piloncillo", "Miel de abeja", "Zacahuil", "Bocoles"],
        min_length=1, max_length=10
    )


def regla_simple(c: dict, productos: list[str]) -> str:
    """Regla de negocio escrita a mano según el clima; devuelve el texto sugerido."""
    if c["precipitacion_mm"] > 0 or c["temperatura_c"] < 20:
        return f"Con {c['descripcion']} y {c['temperatura_c']} ◦C, recomiende {productos[0]}."
    return f"Con {c['temperatura_c']} ◦C, recomiende {productos[-1]} para llevar."


# ---------------------------------------------------------------- Historial
# Memoria del proceso o base de datos en la nube: se usa Supabase solo si
# están definidas las dos variables de entorno.
ALMACEN = "supabase" if (SUPABASE_URL and SUPABASE_KEY) else "memoria"
_historial: list[dict] = [] # se pierde al reiniciar o en otra instancia


def _cabeceras_supabase() -> dict:
    """Cabeceras de autenticación que exige la API REST de Supabase (PostgREST)."""
    h = {"apikey": SUPABASE_KEY}
    # Las llaves heredadas son JWT (empiezan con "eyJ") y también van en Authorization
    if SUPABASE_KEY.startswith("eyJ"):
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return h


def guardar_consulta(registro: dict) -> dict:
    """Guarda una consulta en memoria o en la tabla consultas de Supabase.
    Devuelve el registro guardado, con su id y fecha de creación.
    """
    if ALMACEN == "memoria":
        registro = {
            "id": len(_historial) + 1,
            "creado": time.strftime(" %Y- %m- %dT %H: %M: %S"),
            **registro
        }
        _historial.append(registro)
        return registro
    # POST /rest/v1/<tabla> inserta una fila. "Prefer: return=representation"
    # pide a Supabase que devuelva la fila creada (con id y fecha del servidor).
    filas = llamar(
        "POST", f"{SUPABASE_URL}/rest/v1/consultas", json=registro,
        headers={**_cabeceras_supabase(), "Prefer": "return=representation"}
    )
    return filas[0] # PostgREST devuelve una lista de filas


def leer_historial(limite: int) -> list[dict]:
    """Devuelve las últimas consultas, de la más reciente a la más antigua."""
    if ALMACEN == "memoria":
        return list(reversed(_historial))[:limite]
    # PostgREST traduce los parámetros de la URL a SQL:
    # SELECT * FROM consultas ORDER BY creado DESC LIMIT <limite>
    return llamar(
        "GET", f"{SUPABASE_URL}/rest/v1/consultas",
        headers=_cabeceras_supabase(),
        params={"select": "*", "order": "creado.desc", "limit": limite}
    )


@app.post("/recomendacion")
def recomendacion(s: SolicitudRecomendacion):
    """Combina el clima con una regla de negocio y guarda la consulta en el historial.
    Responde 200 con el clima, la recomendación y el registro guardado; 404 si la
    ciudad no existe, 422 si el cuerpo no es válido y 502/503/504 si falla un
    servicio externo.
    """
    c = clima(s.ciudad)
    texto = regla_simple(c, s.productos)
    t0 = time.perf_counter() # se mide cuánto tarda guardar en el almacén
    registro = guardar_consulta({
        "ciudad": c["ciudad"],
        "temperatura_c": c["temperatura_c"],
        "descripcion": c["descripcion"],
        "recomendacion": texto
    })
    return {
        "clima": c, "recomendacion": texto, "registro": registro, "almacen": ALMACEN,
        "latencia_guardado_ms": round((time.perf_counter() - t0) * 1000, 1)
    }


@app.get("/historial")
def historial(limite: int = Query(10, ge=1, le=100)):
    """Lista las últimas consultas; limite va de 1 a 100 (fuera de rango -> 422)."""
    filas = leer_historial(limite)
    return {"almacen": ALMACEN, "total": len(filas), "consultas": filas}
