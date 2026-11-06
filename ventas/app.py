"""Microservicio Ventas de TiendaIA (Laboratorio 2).
Registra ventas en Redis (base de datos clave-valor en memoria). Antes de guardar
una venta consulta a los microservicios Clientes y Productos por HTTP
(comunicación síncrona) para validar que existan y obtener el precio.
El servicio de IA le pide la lista de ventas para entrenar su modelo.
"""
import json
import os
from datetime import date
import redis
import requests  # cliente HTTP para llamar a otros microservicios
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- Configuración
# Conexión a Redis. "redis" es el nombre del contenedor en docker-compose.yml.
# decode_responses=True hace que Redis devuelva str en lugar de bytes.
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)

# Las URL se leen de variables de entorno: en Docker Compose cada servicio se
# llama por su nombre (http://clientes:8000); fuera de Docker se pueden cambiar.
CLIENTES_URL = os.getenv("CLIENTES_URL", "http://clientes:8000")
PRODUCTOS_URL = os.getenv("PRODUCTOS_URL", "http://productos:8000")

app = FastAPI(title="TiendaIA - Ventas")
TIEMPO_ESPERA = 5  # segundos: nunca esperar para siempre a otro servicio
sesion = (
    requests.Session()
)  # reutiliza conexiones TCP entre peticiones (más rápido)


# ---------------------------------------------------------------- Modelo de entrada
class VentaIn(BaseModel):
    """Datos de una venta. Si no son válidos, FastAPI responde 422."""

    # Field(gt=0): los id deben ser mayores que 0; le=1000: cantidad máxima 1000
    cliente_id: int = Field(gt=0)
    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=1000)
    fecha: date | None = None  # si no se envía: hoy


def consultar(url: str):
    """Llamada síncrona a otro microservicio; None si no existe el recurso.
    Recibe la URL completa y devuelve el JSON de la respuesta. Si el otro servicio
    falla (500, 503...) o no responde a tiempo, se lanza una excepción de requests.
    """
    resp = sesion.get(url, timeout=TIEMPO_ESPERA)
    if resp.status_code == 404:  # el recurso no existe: no es un error del sistema
        return None
    resp.raise_for_status()  # cualquier otro error (500, 503...) lanza excepción
    return resp.json()


# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Verificación de salud (200). Incluye si Redis responde a PING."""
    return {"servicio": "ventas", "status": "ok", "redis": r.ping()}


@app.post("/ventas", status_code=201)
def crear(v: VentaIn):
    """Registra una venta y devuelve el registro completo con id, precio y total.
    Responde 201 (Created) si se guardó, o 422 si el cliente o el producto no
    existen (los datos enviados no se pueden procesar) o el cuerpo es inválido.
    """
    # Validación entre servicios: Ventas no tiene acceso a las bases de datos de
    # Clientes ni de Productos; solo puede preguntarles por su API HTTP.
    if consultar(f"{CLIENTES_URL}/clientes/{v.cliente_id}") is None:
        raise HTTPException(422, "El cliente no existe")
    producto = consultar(f"{PRODUCTOS_URL}/productos/{v.producto_id}")
    if producto is None:
        raise HTTPException(422, "El producto no existe")

    # INCR: suma 1 a la clave de forma atómica y devuelve el nuevo valor.
    # Sirve como id autoincremental sin repetidos, aun con peticiones simultáneas.
    venta_id = r.incr("venta:siguiente_id")

    # Se guarda el precio del momento de la venta (si después cambia el precio
    # del producto, la venta conserva el valor original).
    venta = {
        "id": venta_id,
        **v.model_dump(mode="json"),
        "fecha": (v.fecha or date.today()).isoformat(),
        "precio": producto["precio"],
        "total": round(producto["precio"] * v.cantidad, 2),
    }

    # Cada venta es una clave de texto "venta:<id>" con el JSON como valor
    r.set(f"venta:{venta_id}", json.dumps(venta))
    r.rpush("ventas", venta_id)  # lista ordenada de ids
    return venta


@app.get("/ventas")
def listar():
    """Devuelve todas las ventas en orden de registro (200)."""
    ids = r.lrange("ventas", 0, -1)  # LRANGE 0 -1: toda la lista de ids
    if not ids:
        return []
    # MGET trae muchas claves en una sola ida y vuelta a Redis (más eficiente
    # que un GET por venta). "if v" descarta claves que ya no existan.
    return [json.loads(v) for v in r.mget([f"venta:{i}" for i in ids]) if v]


@app.get("/ventas/{venta_id}")
def obtener(venta_id: int):
    """Devuelve una venta por su id (200) o 404 si no existe."""
    v = r.get(f"venta:{venta_id}")
    if v is None:
        raise HTTPException(404, "Venta no encontrada")
    return json.loads(v)  # el valor se guardó como texto JSON


@app.delete("/ventas/{venta_id}", status_code=204)
def eliminar(venta_id: int):
    """Borra una venta. Responde 204 (sin contenido) o 404 si no existe."""
    # DEL devuelve cuántas claves borró: 0 significa que no existía
    if r.delete(f"venta:{venta_id}") == 0:
        raise HTTPException(404, "Venta no encontrada")
    r.lrem("ventas", 0, venta_id)  # también se quita su id de la lista