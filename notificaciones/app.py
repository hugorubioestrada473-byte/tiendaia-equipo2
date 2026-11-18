"""Microservicio Notificaciones de TiendaIA (Laboratorio 3).
TODO: describan en 3 a 5 líneas qué hace este servicio y con quién se comunica.
"""
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
import pika  # cliente de RabbitMQ (protocolo AMQP)
import redis
from fastapi import FastAPI, Query

# -------------------------------- Configuración --------------------------------
RABBIT = os.getenv("RABBITMQ_HOST", "rabbitmq")
# Nombre del host (local) o URL amqp(s):// de un servicio administrado (CloudAMQP)
PARAMS = (pika.URLParameters(RABBIT) if "://" in RABBIT
          else pika.ConnectionParameters(RABBIT))
EXCHANGE = "tienda.events"  # el mismo exchange en el que publica Ventas
COLA = "notificaciones"     # cola PROPIA de este servicio
PATRON = "venta.*"          # binding: recibe venta.creada, venta.cancelada, etc.
MAXIMO = 100                # cuántos avisos se conservan en Redis

# decode_responses=True: Redis devuelve str en lugar de bytes
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
logging.basicConfig(level=logging.INFO)

# -------------------------------- Consumidor --------------------------------
def al_recibir(canal, metodo, props, cuerpo):
    """Callback de pika: se ejecuta una vez por cada evento recibido.
    Recibe el canal, los datos de entrega (metodo.routing_key es el tipo de
    evento y metodo.delivery_tag lo identifica), las propiedades y el cuerpo en
    bytes. Guarda el aviso en Redis y confirma con ack; si el evento está
    dañado, lo descarta con nack.
    """
    try:
        venta = json.loads(cuerpo)  # bytes con JSON -> dict
        # Ej.: "Venta 401: cliente 1 compró 2 x producto 1 ($70.0)"
        texto = (f"Venta {venta['id']}: cliente {venta['cliente_id']} compró "
                 f"{venta['cantidad']} x producto {venta['producto_id']} "
                 f"(${venta['total']})")
    except (ValueError, KeyError, TypeError) as e:
        # Evento "venenoso": se registra y se descarta. requeue=False evita que
        # vuelva a la cola y falle una y otra vez para siempre.
        logging.warning("Evento inválido descartado (%s): %r, cuerpo[:200]")
        canal.basic_nack(delivery_tag=metodo.delivery_tag, requeue=False)
        return

    aviso = {"evento": metodo.routing_key, "mensaje": texto}
    
    # LPUSH agrega al INICIO (el más reciente queda primero) y LTRIM recorta
    # la lista a los MAXIMO más nuevos para que no crezca sin límite.
    r.lpush("notificaciones", json.dumps(aviso))
    r.ltrim("notificaciones", 0, MAXIMO - 1)
    
    # ack al FINAL, después de guardar: si el servicio muere antes, RabbitMQ
    # conserva el mensaje y lo vuelve a entregar al reconectar (no se pierde).
    canal.basic_ack(delivery_tag=metodo.delivery_tag)

def consumir():
    """Conecta, declara exchange/cola/binding y consume para siempre.
    Si RabbitMQ aún no arranca o se reinicia, espera y vuelve a intentar.
    """
    while True:
        try:
            con = pika.BlockingConnection(PARAMS)
            canal = con.channel()
            # Declarar es idempotente: no importa si Ventas o este servicio
            # arranca primero
            canal.exchange_declare(EXCHANGE, exchange_type="topic",
                                   durable=True)
            # durable=True: la cola sobrevive a un reinicio de RabbitMQ y guarda
            # los eventos que lleguen mientras este servicio está apagado.
            canal.queue_declare(queue=COLA, durable=True)
            canal.queue_bind(COLA, EXCHANGE, routing_key=PATRON)
            canal.basic_consume(COLA, al_recibir)
            logging.info("Notificaciones escuchando %s en %s", PATRON, EXCHANGE)
            canal.start_consuming()  # bloquea y llama al_recibir() por evento
        except pika.exceptions.AMQPConnectionError:
            logging.warning("RabbitMQ no disponible; reintento en 3 s")
            time.sleep(3)
        except redis.RedisError as e:
            # Redis caído: el evento no se confirmó y RabbitMQ lo reentregará
            logging.warning("Redis no disponible (%s); reintento en 3 s", e)
            time.sleep(3)

# -------------------------------- Arranque de la API --------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Se ejecuta al iniciar la API: lanza el consumidor en un hilo aparte.
    start_consuming() bloquea; en el hilo principal congelaría a FastAPI.
    daemon=True: el hilo termina solo cuando se detiene el servidor.
    """
    threading.Thread(target=consumir, daemon=True).start()
    yield  # aquí la API atiende peticiones; lo que siga se ejecuta al apagar

app = FastAPI(title="TiendaIA - Notificaciones", lifespan=lifespan)

# -------------------------------- Endpoints --------------------------------
@app.get("/health")
def salud():
    """Verificación de salud usada por el gateway; responde 200."""
    return {"servicio": "notificaciones", "status": "ok"}

@app.get("/notificaciones")
def listar(limite: int = Query(20, ge=1, le=MAXIMO)):
    try:
        resultados = []
        elementos = r.lrange("notificaciones", 0, limite - 1)
        for x in elementos:
            try:
                resultados.append(json.loads(x))
            except Exception:
                resultados.append({"mensaje": str(x)})
        return resultados
    except Exception as e:
        print(f"ERROR EN REDIS/ENDPOINT: {e}")
        return {"error": str(e)}