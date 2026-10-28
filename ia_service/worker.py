"""Worker de inferencia de TiendaIA (Laboratorio 3): consume la cola 'inferencias'.
Proceso independiente (no es una API): toma solicitudes de RabbitMQ, calcula la
predicción con el modelo entrenado por el servicio de IA y escribe el resultado
en Redis, donde lo lee GET /ia/solicitudes/{id}. Puede haber N copias en
paralelo: RabbitMQ reparte los mensajes entre ellas (cola de trabajo).
"""
import json
import os
import socket
import time
import joblib
import pandas as pd
import pika # cliente de RabbitMQ (protocolo AMQP)
import redis
# ---------------------------------------------------------------- Configuración
RABBIT = os.getenv("RABBITMQ_HOST", "rabbitmq")
# Nombre del host (local) o URL amqp(s):// de un servicio administrado (CloudAMQP)
PARAMS = (pika.URLParameters(RABBIT) if "://" in RABBIT
else pika.ConnectionParameters(RABBIT))
MODELO = os.getenv("MODELO_PATH", "/modelos/modelo.joblib")
RETARDO = float(os.getenv("RETARDO_MS", "200")) / 1000 # simula un modelo pesado
r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), decode_responses=True)
modelo = None # se carga la primera vez que se necesita
def procesar(canal, metodo, props, cuerpo):
    """Callback que pika llama por cada mensaje recibido de la cola.
    Recibe el canal, los datos de entrega (metodo.delivery_tag identifica el
    mensaje), las propiedades y el cuerpo en bytes. Guarda el resultado en Redis
    y confirma con ack; si algo falla, marca error y rechaza con nack.
    """
    global modelo
    try:
        s = json.loads(cuerpo)
        if modelo is None:
            modelo = joblib.load(MODELO) # se carga una sola vez
        x = pd.DataFrame([[s["producto_id"], s["mes"], s["precio"]]],
                        columns=["producto_id", "mes", "precio"])
        time.sleep(RETARDO)
        # "worker" = host:pid, permite ver qué copia atendió cada solicitud
        resultado = {"estado": "listo",
                    "worker": f"{socket.gethostname()}:{os.getpid()}",
                    "cantidad_estimada": round(float(modelo.predict(x)[0]), 1)}
    except Exception as e: # no detener al worker
        print("error al procesar:", e, flush=True)
        # Si el JSON sí se pudo leer y trae id, se avisa al cliente del error
        if isinstance(locals().get("s"), dict) and "id" in s:
            r.set(f"solicitud:{s['id']}",
        json.dumps({"estado": "error", "detalle": str(e)}), ex=3600)
        # nack con requeue=False: se descarta el mensaje. Si se reencolara, un
        # mensaje dañado ("venenoso") fallaría una y otra vez para siempre.
        canal.basic_nack(delivery_tag=metodo.delivery_tag, requeue=False)
        return
    r.set(f"solicitud:{s['id']}", json.dumps(resultado), ex=3600)
    # ack = "ya terminé, bórralo de la cola". Se envía AL FINAL: si el worker
    # muere a medio cálculo, RabbitMQ entrega el mensaje a otro worker.
    canal.basic_ack(delivery_tag=metodo.delivery_tag) # confirmar AL FINAL
    # ---------------------------------------------------------------- Ciclo principal
while True:
    try:
        con = pika.BlockingConnection(PARAMS)
        canal = con.channel()
        canal.queue_declare("inferencias", durable=True) # misma cola que cola.py
        # prefetch_count=1: RabbitMQ no le da otro mensaje a este worker hasta que
        # confirme el actual. Así un worker lento no acapara la cola.
        canal.basic_qos(prefetch_count=1) # reparto justo
        canal.basic_consume("inferencias", procesar)
        print("worker listo", flush=True)
        canal.start_consuming() # bloquea y llama procesar() por mensaje
    except pika.exceptions.AMQPConnectionError:
        time.sleep(3) # RabbitMQ aún no arranca o se reinició: reintentar