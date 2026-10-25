"""Mide latencia de GET /api/productos/1 y POST /api/ventas (Laboratorio 2).
Uso: python scripts/medir_lab2.py [URL_GATEWAY] [N]
"""
import statistics as st
import sys
import time
import requests

GW = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 100
sesion = requests.Session()  # reutiliza la conexión, como un cliente real
VENTA = {"cliente_id": 1, "producto_id": 1, "cantidad": 1, "fecha": "2025-06-15"}


def medir(metodo, url, **opciones):
    """Hace N peticiones e imprime la media y el percentil 95 en milisegundos."""
    tiempos = []
    for _ in range(N):
        t = time.perf_counter()
        r = sesion.request(metodo, url, timeout=10, **opciones)
        tiempos.append((time.perf_counter() - t) * 1000)
        r.raise_for_status()  # detiene la medición si hay un error 4xx o 5xx
    tiempos.sort()
    print(
        f"{metodo} {url}: media={st.mean(tiempos):.1f} ms "
        f"p95={tiempos[int(0.95 * N) - 1]:.1f} ms"
    )


medir("GET", f"{GW}/api/productos/1")
medir("POST", f"{GW}/api/ventas", json=VENTA)