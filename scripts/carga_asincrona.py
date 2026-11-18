"""Envía N solicitudes de inferencia asíncronas y mide el tiempo hasta que todas terminan.
Se usa en el laboratorio de mensajería: el servicio IA encola cada solicitud y
responde de inmediato con un id; los workers la procesan después. Este script
consulta el estado de cada id hasta que todas terminan y cuenta cuántas hizo cada worker.
Uso: python scripts/carga_asincrona.py [URL_GATEWAY] [N]
"""
import os
import sys
import time
from collections import Counter
import requests # cliente HTTP para llamar al gateway
# ---------------------------------------------------------------- Configuración
GW = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 100
TOKEN = os.getenv("TOKEN") # desde el Lab. 6: JWT de analista o admin
TIEMPO_ESPERA = 10 # segundos: nunca esperar para siempre al gateway
sesion = requests.Session() # reutiliza conexiones TCP entre peticiones (más rápido)
if TOKEN:
# Las cabeceras de la sesión se envían en TODAS las peticiones
    sesion.headers.update({"Authorization": f"Bearer {TOKEN}"})
# ---------------------------------------------------------------- Envío
# Cada POST solo encola el trabajo: la respuesta trae el id, no el resultado
t0 = time.perf_counter()
ids = [sesion.post(f"{GW}/api/ia/solicitudes", timeout=TIEMPO_ESPERA,
json={"producto_id": 1 + i % 5, "mes": 1 + i % 12,
"precio": 90.0}).json()["id"]
for i in range(N)]
t_envio = time.perf_counter() - t0
# ---------------------------------------------------------------- Sondeo (polling)
# Se pregunta periódicamente por cada solicitud pendiente hasta que termine
pendientes, por_worker = set(ids), Counter() # Counter: diccionario que cuenta
while pendientes:
    for sid in list(pendientes): # copia: el conjunto cambia dentro del ciclo
        res = sesion.get(f"{GW}/api/ia/solicitudes/{sid}", timeout=TIEMPO_ESPERA).json()
        if res["estado"] == "listo":
            pendientes.discard(sid)
            por_worker[res["worker"]] += 1 # qué réplica del worker la procesó
        elif res["estado"] == "error": # el worker no pudo procesarla
            pendientes.discard(sid)
por_worker["errores"] += 1
time.sleep(0.2) # pausa para no saturar al gateway
total = time.perf_counter() - t0
# Rendimiento (throughput) = solicitudes completadas por segundo
print(f"N={N} envío={t_envio:.1f}s total={total:.1f}s "
    f"rendimiento={N / total:.1f} sol/s por worker={dict(por_worker)}")