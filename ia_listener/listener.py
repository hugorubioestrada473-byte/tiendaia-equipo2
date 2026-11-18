"""Microservicio IA-Listener de TiendaIA (Laboratorio 3, Parte G).
Segundo suscriptor independiente que escucha los eventos 'venta.*' de RabbitMQ,
cuenta las ventas en Redis y solicita el reentrenamiento de la IA cada 50 ventas.
"""

import os
import time
import pika
import redis
import requests

# Configuración de conexiones mediante variables de entorno
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
IA_URL = os.getenv("IA_URL", "http://ia:8000")

EXCHANGE_NAME = "tienda.eventos"
QUEUE_NAME = "ia_listener"
ROUTING_KEY = "venta.*"


def conectar_servicios():
  """Establece la conexión con Redis y RabbitMQ aplicando un ciclo de reconexión."""
  r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

  while True:
    try:
      print(f"[*] Conectando a RabbitMQ en {RABBITMQ_HOST}...", flush=True)
      connection = pika.BlockingConnection(
          pika.ConnectionParameters(host=RABBITMQ_HOST)
      )
      channel = connection.channel()
      print("[x] Conectado exitosamente a RabbitMQ", flush=True)
      return r, channel
    except pika.exceptions.AMQPConnectionError:
      print(
          "[!] RabbitMQ no disponible todavía. Reintentando en 3 segundos...",
          flush=True,
      )
      time.sleep(3)


def callback(ch, method, properties, body):
  """Callback ejecutado por pika por cada evento de venta recibido."""
  try:
    r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

    # 1. Incrementar el contador de ventas en Redis
    n = r.incr("ia_listener:ventas")
    print(f"[.] Venta detectada. Total en ia_listener: {n}", flush=True)

    # 2. Cada 50 ventas, solicitar el reentrenamiento del modelo
    if n % 50 == 0:
      print(
          f"[!] ¡Límite de 50 ventas alcanzado! Solicitando reentrenamiento a"
          f" {IA_URL}/ia/train...",
          flush=True,
      )
      try:
        response = requests.post(f"{IA_URL}/ia/train", timeout=120)
        print(
            f"[Response] Código de estado de reentrenamiento:"
            f" {response.status_code}",
            flush=True,
        )
      except requests.RequestException as e:
        print(f"[Error] No se pudo conectar con el servicio IA: {e}", flush=True)

    # 3. Confirmar con basic_ack al finalizar correctamente
    ch.basic_ack(delivery_tag=method.delivery_tag)

  except Exception as e:
    print(f"[Error] Fallo al procesar el mensaje: {e}", flush=True)
    # Descartar mensajes venenosos con basic_nack (requeue=False)
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


if __name__ == "__main__":
  r, channel = conectar_servicios()

  # Declarar el exchange, la cola durable propia y su binding
  channel.exchange_declare(
      exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
  )
  channel.queue_declare(queue=QUEUE_NAME, durable=True)
  channel.queue_bind(
      queue=QUEUE_NAME, exchange=EXCHANGE_NAME, routing_key=ROUTING_KEY
  )

  channel.basic_qos(prefetch_count=1)
  channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

  print(
      " [*] Ciclo de reconexión activo. Esperando eventos en la cola"
      " 'ia_listener'...",
      flush=True,
  )
  try:
    channel.start_consuming()
  except KeyboardInterrupt:
    channel.stop_consuming()