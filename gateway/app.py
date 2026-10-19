"""API Gateway de TiendaIA: punto único de entrada (Laboratorio 2).
Recibe todas las peticiones externas en /api/<servicio>/... y las reenvía
(proxy inverso) al microservicio correspondiente: Clientes, Productos, Ventas o IA.
El usuario solo conoce la dirección del gateway; los microservicios quedan ocultos
en la red interna de Docker. También ofrece /health con el estado de cada servicio.
"""
import os
import requests  # cliente HTTP para reenviar las peticiones a los microservicios
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------- Configuración
# Tabla de ruteo: prefijo de la URL -> dirección interna del microservicio.
# En Docker Compose cada servicio se llama por su nombre (http://clientes:8000).
RUTAS = {
    "clientes": os.getenv("CLIENTES_URL", "http://clientes:8000"),
    "productos": os.getenv("PRODUCTOS_URL", "http://productos:8000"),
    "ventas": os.getenv("VENTAS_URL", "http://ventas:8000"),
    "ia": os.getenv("IA_URL", "http://ia:8000"),
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

# Se reutiliza: conexiones persistentes (no se abre una conexión TCP nueva cada vez)
sesion = requests.Session()
TIEMPO_ESPERA = 60  # segundos; generoso porque entrenar el modelo tarda
TIEMPO_SALUD = 3  # /health debe contestar rápido o se considera caído

# ---------------------------------------------------------------- Endpoints
@app.get("/health")
async def salud():
    """Consulta /health de cada microservicio y resume su estado (200).
    Devuelve {"gateway": "ok", "servicios": {"clientes": true, ...}}; un servicio
    aparece en false si no responde 200 o no se pudo conectar con él.
    """
    estado = {}
    for nombre, url in RUTAS.items():
        try:
            # requests es bloqueante: run_in_threadpool lo ejecuta en otro hilo
            # para que el gateway siga atendiendo otras peticiones mientras espera.
            r = await run_in_threadpool(
                sesion.get, f"{url}/health", timeout=TIEMPO_SALUD
            )

            estado[nombre] = r.status_code == 200
        except requests.RequestException:  # caído, sin red o tardó demasiado
            estado[nombre] = False
    return {"gateway": "ok", "servicios": estado}


@app.api_route("/api/{svc}", methods=["GET", "POST"])
@app.api_route("/api/{svc}/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(svc: str, req: Request, ruta: str = ""):
    """Reenvía la petición al microservicio indicado y devuelve su respuesta tal cual.
    Ejemplo: GET /api/clientes/3 -> GET http://clientes:8000/clientes/3.
    Se copian el método, los parámetros de consulta, el cuerpo y el content-type;
    el código HTTP de respuesta (200, 201, 204, 404, 422...) es el del servicio.
    Responde 404 si el servicio no está en la tabla RUTAS.
    """
    if svc not in RUTAS:
        return Response(status_code=404)  # prefijo desconocido
    
    destino = f"{RUTAS[svc]}/{svc}" + (f"/{ruta}" if ruta else "")
    cuerpo = await req.body()  # bytes del cuerpo (vacío en GET)
    
    # requests es BLOQUEANTE: si se llamara directamente, el gateway (asíncrono)
    # se congelaría mientras espera al microservicio y no atendería a nadie más.
    # run_in_threadpool ejecuta la llamada en un hilo aparte y await espera su
    # resultado sin bloquear el ciclo de eventos.
    r = await run_in_threadpool(
        sesion.request,
        req.method,
        destino,
        # multi_items() conserva parámetros repetidos (?a=1&a=2)
        params=list(req.query_params.multi_items()),
        data=cuerpo,
        headers={"content-type": req.headers.get("content-type", "application/json")},
        timeout=TIEMPO_ESPERA,
        # No seguir redirecciones: el gateway devuelve la respuesta tal cual
        allow_redirects=False,
    )
    
    # Se devuelve el cuerpo, el código y el tipo de contenido del microservicio
    return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))