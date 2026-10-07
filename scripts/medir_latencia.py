"""Mide la latencia de un endpoint desplegado en la nube (Laboratorio 1).
Hace una primera petición (que puede sufrir un arranque en frío si la función
serverless estaba "dormida") y luego N peticiones más para calcular p50, p95 y máximo.
Uso: python scripts/medir_latencia.py https://mi-app.vercel.app/clima 30
"""
import statistics as st
import sys
import time
import requests # cliente HTTP para llamar al endpoint

URL = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30

# 60 s: un arranque en frío puede tardar varios segundos, pero no se espera para siempre
TIEMPO_ESPERA = 60

# La sesión reutiliza la conexión TCP/TLS: así se mide el servicio, no el saludo TLS
with requests.Session() as sesion:
    t = time.perf_counter() # reloj de alta precisión para medir duraciones
    r = sesion.get(URL, timeout=TIEMPO_ESPERA)
    primera = (time.perf_counter() - t) * 1000 # segundos -> milisegundos

    tiempos, errores = [], 0
    for _ in range(N):
        t = time.perf_counter()
        # True cuenta como 1: se suman las respuestas con código de error (>= 400)
        errores += sesion.get(URL, timeout=TIEMPO_ESPERA).status_code >= 400
        tiempos.append((time.perf_counter() - t) * 1000)

    # Percentiles: p50 = la mitad de las peticiones tardó menos que esto;
    # p95 = el 95 % tardó menos (refleja la experiencia de los usuarios más lentos)
    tiempos.sort()
    print(f"URL: {URL}")
    print(f"primera petición: {primera:.0f} ms (código {r.status_code})")
    print(
        f"siguientes {N}: p50={st.median(tiempos):.0f} ms "
        f"p95={tiempos[int(0.95 * N) - 1]:.0f} ms "
        f"máx={tiempos[-1]:.0f} ms errores={errores}"
    )