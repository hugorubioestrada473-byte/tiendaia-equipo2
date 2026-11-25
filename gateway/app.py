"""API Gateway de TiendaIA: punto único de entrada a todos los microservicios.
Lab. 2: enrutamiento | Lab. 3: notificaciones | Lab. 4: imágenes
Lab. 6: autenticación (JWT), autorización por roles y API Key hacia los servicios.
Recibe /api/<servicio>/..., revisa el JWT del usuario y sus roles y, si tiene permiso,
reenvía la petición al microservicio correspondiente agregando la API Key del gateway.
"""
import os
import jwt  # PyJWT: verificación de los tokens emitidos por el Auth-Service
import requests  # cliente HTTP para reenviar peticiones a los microservicios
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------- Configuración
# Tabla de enrutamiento: nombre en la URL pública -> dirección interna del servicio.
# Dentro de Docker Compose cada servicio se alcanza por su nombre (http://clientes:8000).
RUTAS = {
    "clientes": os.getenv("CLIENTES_URL", "http://clientes:8000"),
    "productos": os.getenv("PRODUCTOS_URL", "http://productos:8000"),
    "ventas": os.getenv("VENTAS_URL", "http://ventas:8000"),
    "ia": os.getenv("IA_URL", "http://ia:8000"),
    "notificaciones": os.getenv("NOTIF_URL", "http://notificaciones:8000"),  # Lab. 3
    "imagenes": os.getenv("IMAGENES_URL", "http://imagenes:8000"),  # Lab. 4
    "auth": os.getenv("AUTH_URL", "http://auth:8000"),  # Lab. 6
}

# Mismo secreto que usa Auth para firmar: así el gateway verifica los JWT por sí
# mismo, sin preguntarle a Auth en cada petición. Vacío = sin autenticación.
JWT_SECRET = os.getenv("JWT_SECRET", "")
API_KEY = os.getenv("API_KEY", "")  # identidad del gateway ante los servicios

# ---------------------------------------------------------------- Permisos (roles)
# PUBLICO: combinaciones (método, servicio) que no requieren token: ver el catálogo,
# ver imágenes e iniciar sesión (sin esto nadie podría obtener su primer token).
PUBLICO = {("GET", "productos"), ("GET", "imagenes"), ("POST", "auth")}

# (método, servicio) -> roles permitidos. 'admin' puede todo. Lo no listado: solo admin
# (principio de mínimo privilegio: lo que no se permite explícitamente se niega).
PERMISOS = {
    ("GET", "clientes"): {"vendedor", "analista"},
    ("POST", "clientes"): {"vendedor"},
    ("PUT", "clientes"): {"vendedor"},
    ("GET", "ventas"): {"vendedor", "analista"},
    ("POST", "ventas"): {"vendedor"},
    ("GET", "ia"): {"analista"},
    ("POST", "ia"): {"analista"},  # excepto /ia/train (ver abajo)
    ("GET", "notificaciones"): {"vendedor"},
}

app = FastAPI(title="TiendaIA - API Gateway")

# CORS (Cross-Origin Resource Sharing): el navegador bloquea las peticiones de una
# página a OTRO origen (esquema + host + puerto) salvo que el servidor lo autorice.
# El cliente web vive en otro origen (http://localhost:5500, Render...), por eso el
# gateway responde con las cabeceras Access-Control-Allow-*. CORS_ORIGINS es una
# lista separada por comas; "*" permite cualquier origen (en producción, ponga
# solo la URL de su frontend).
ORIGENES = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sesión de requests: reutiliza conexiones TCP con los servicios (conexiones
# persistentes), lo que ahorra tiempo en cada petición reenviada.
sesion = requests.Session()

# Tiempo máximo de espera por respuesta (s). Es amplio porque algunos servicios,
# como IA o imágenes, pueden tardar; requests lo recibe en CADA llamada.
TIEMPO_ESPERA = 60


# ---------------------------------------------------------------- Autorización
def autorizar(metodo: str, svc: str, ruta: str, auth: str | None):
    """Decide si la petición puede pasar.
    Recibe el método HTTP, el servicio destino, el resto de la ruta y la cabecera
    Authorization. Devuelve (usuario, None) si se permite, o (None, respuesta de
    error): 401 si falta el token o no es válido, 403 si el rol no alcanza.
    """
    if (metodo, svc) in PUBLICO:
        return "anonimo", None
    if not JWT_SECRET:  # Labs. 2 a 5: sin autenticación
        return "anonimo", None

    # El token llega como "Authorization: Bearer <jwt>".
    if not auth or not auth.lower().startswith("bearer "):
        return None, JSONResponse({"detail": "Token requerido"}, 401)
    try:
        # auth[7:] quita el prefijo "Bearer ". decode comprueba la firma (que nadie
        # alteró el contenido) y que el token no haya expirado (claim "exp").
        datos = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None, JSONResponse({"detail": "Token inválido o expirado"}, 401)

    roles = set(datos.get("roles", []))
    permitidos = PERMISOS.get((metodo, svc), set())
    if svc == "ia" and ruta.startswith("train"):
        permitidos = set()  # reentrenar el modelo: solo admin

    # roles & permitidos es la intersección de conjuntos: basta con un rol en común.
    if "admin" in roles or roles & permitidos:
        return datos["sub"], None

    # El usuario sí se identificó (token válido), pero no tiene permiso: 403.
    return None, JSONResponse({"detail": "Permiso insuficiente"}, 403)


# ---------------------------------------------------------------- Endpoints
@app.get("/health")
async def salud():
    """Revisa el /health de cada servicio y reporta cuáles responden (siempre 200)."""
    estado = {}
    for nombre, url in RUTAS.items():
        try:
            # requests es bloqueante: run_in_threadpool la ejecuta en otro hilo para
            # no congelar el gateway mientras espera (timeout corto de 3 s).
            r = await run_in_threadpool(sesion.get, f"{url}/health", timeout=3)
            estado[nombre] = r.status_code == 200
        except requests.RequestException:  # servicio caído o que no responde
            estado[nombre] = False
    return {"gateway": "ok", "servicios": estado}


@app.api_route("/api/{svc}", methods=["GET", "POST"])
@app.api_route("/api/{svc}/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(svc: str, req: Request, ruta: str = ""):
    """Proxy inverso: reenvía /api/<svc>/<ruta> al microservicio <svc>.
    Devuelve tal cual el cuerpo, el código HTTP y el tipo de contenido que responda el
    servicio. Responde 404 si el servicio no existe y 401/403 si no se autoriza.
    """
    if svc not in RUTAS:
        return Response(status_code=404)

    usuario, error = autorizar(req.method, svc, ruta, req.headers.get("authorization"))
    if error:
        return error

    # Cabeceras hacia el servicio: x-api-key identifica al GATEWAY (servicio a
    # servicio) y x-usuario informa qué persona hizo la petición (para auditoría).
    cabeceras = {
        "content-type": req.headers.get("content-type", "application/json"),
        "x-api-key": API_KEY,
        "x-usuario": usuario,
    }

    # Solo Auth necesita el token del usuario (p. ej. el admin registra usuarios).
    if svc == "auth" and req.headers.get("authorization"):
        cabeceras["authorization"] = req.headers["authorization"]

    destino = f"{RUTAS[svc]}/{svc}" + (f"/{ruta}" if ruta else "")

    # requests es BLOQUEANTE y este endpoint es async: si se llamara directo, el
    # gateway completo se congelaría mientras espera al servicio. run_in_threadpool
    # ejecuta la llamada en un hilo aparte y el gateway sigue atendiendo a otros.
    # multi_items() conserva parámetros repetidos (?tag=a&tag=b).
    # allow_redirects=False: se devuelve la respuesta tal cual, sin seguir redirecciones.
    r = await run_in_threadpool(
        sesion.request,
        req.method,
        destino,
        params=list(req.query_params.multi_items()),
        data=await req.body(),
        headers=cabeceras,
        timeout=TIEMPO_ESPERA,
        allow_redirects=False,
    )
    return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))