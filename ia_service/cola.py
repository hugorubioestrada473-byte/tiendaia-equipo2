"""Solicitudes de inferencia asíncronas (cola de trabajo en RabbitMQ, Laboratorio 3).
Rutas que el servicio de IA agrega con include_router. POST encola la solicitud y
responde de inmediato (202) con un id; uno o varios procesos worker.py la toman
de la cola "inferencias", calculan la predicción y escriben el resultado en Redis.
El cliente consulta el estado con GET usando ese id.
"""
import json
import os
import uuid
import pika # cliente de RabbitMQ (protocolo AMQP)
import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
# ---------------------------------------------------------------- Configuración
RABBIT = os.getenv("RABBITMQ_HOST", "rabbitmq")
# Nombre del host (local) o URL amqp(s):// de un servicio administrado (CloudAMQP)
PARAMS = (pika.URLParameters(RABBIT) if "://" in RABBIT
else pika.ConnectionParameters(RABBIT))
COLA = "inferencias" # cola de trabajo compartida por todos los workers
# Redis guarda el estado de cada solicitud; decode_responses=True devuelve str
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
router = APIRouter() # grupo de rutas que app.py incluye en la aplicación
class Solicitud(BaseModel):
    """Datos de entrada; Field(gt=0) exige > 0 y ge/le definen un rango (si no, 422)."""
    producto_id: int = Field(gt=0)
    mes: int = Field(ge=1, le=12)
    precio: float = Field(gt=0)
# ---------------------------------------------------------------- Endpoints
@router.post("/ia/solicitudes", status_code=202)
def encolar(s: Solicitud):
    """Encola una solicitud de inferencia y devuelve su id.
    Responde 202 Accepted: "recibido, se procesará después". No espera al
    modelo; así el cliente no se queda bloqueado si hay muchas solicitudes.
    """
    sid = str(uuid.uuid4()) # id único aleatorio, imposible de adivinar
    # Clave "solicitud:<id>" con el estado en JSON; ex=3600 la borra en 1 hora
    r.set(f"solicitud:{sid}", json.dumps({"estado": "pendiente"}), ex=3600)
    con = pika.BlockingConnection(PARAMS)
    canal = con.channel()
    # durable=True: la cola sobrevive a un reinicio de RabbitMQ. Declararla es
    # idempotente: si ya existe no pasa nada, y así no importa quién arranca primero.
    canal.queue_declare(COLA, durable=True)
    # Exchange "" (por omisión): entrega el mensaje directo a la cola llamada COLA.
    # delivery_mode=2 = mensaje persistente (se guarda en disco, no se pierde).
    canal.basic_publish("", COLA, json.dumps({"id": sid, **s.model_dump()}),
    pika.BasicProperties(delivery_mode=2))
    con.close()
    return {"id": sid, "estado": "pendiente"}
@router.get("/ia/solicitudes/{sid}")
def consultar(sid: str):
    """Devuelve el estado de una solicitud: pendiente, listo (con resultado) o error.
    Responde 404 si el id no existe o ya expiró en Redis.
    """
    v = r.get(f"solicitud:{sid}")
    if v is None:
        raise HTTPException(404, "Solicitud no encontrada")
    return {"id": sid, **json.loads(v)}