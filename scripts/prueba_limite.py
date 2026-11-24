"""Prueba el límite de peticiones (rate limiting) del proxy perimetral (Laboratorio 5).

Lanza una ráfaga de peticiones simultáneas contra una URL del Nginx perimetral y
cuenta cuántas fueron aceptadas (200) y cuántas rechazadas por exceso (429 Too
Many Requests). Con limit_req de 10 peticiones/s y burst=20, Nginx deja esperando
en fila hasta 20 peticiones; con 50 hilos la fila se llena y, de 150 peticiones,
solo pasan unas 20 a 30: las demás reciben 429.

Uso:
    python scripts/prueba_limite.py [URL] [PETICIONES] [HILOS]
Ej.:
    python scripts/prueba_limite.py http://localhost:8081/api/productos 150 50
"""

import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

# ---------------------------------------------------------------- Configuración
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081/api/productos"
TOTAL = int(sys.argv[2]) if len(sys.argv) > 2 else 150  # peticiones de la ráfaga
# Peticiones simultáneas: deben ser más que el burst (20) para llenar la fila
HILOS = int(sys.argv[3]) if len(sys.argv) > 3 else 50
TIEMPO_ESPERA = 10  # segundos por petición


def pedir(_):
    """Hace un GET y devuelve el código HTTP (0 si no hubo respuesta)."""
    try:
        return requests.get(URL, timeout=TIEMPO_ESPERA).status_code
    except requests.RequestException:  # conexión rechazada o tiempo agotado
        return 0


# ---------------------------------------------------------------- Programa principal
if __name__ == "__main__":
    print(f"Ráfaga de {TOTAL} peticiones a {URL} con {HILOS} hilos...")
    inicio = time.perf_counter()

    # ThreadPoolExecutor reparte las TOTAL peticiones entre HILOS hilos: así
    # llegan casi al mismo tiempo, como un cliente abusivo o un bot.
    with ThreadPoolExecutor(max_workers=HILOS) as grupo:
        codigos = list(grupo.map(pedir, range(TOTAL)))

    duracion = time.perf_counter() - inicio
    conteo = Counter(codigos)  # cuenta cuántas veces aparece cada código

    print(f"Duración: {duracion:.2f} s ({TOTAL / duracion:.1f} peticiones/s)")
    for codigo, veces in sorted(conteo.items()):
        nombre = {
            200: "OK",
            429: "Too Many Requests (límite)",
            0: "sin respuesta",
        }.get(codigo, "")
        print(f"  {codigo:>3}  {veces:>4}  {nombre}")

    if conteo.get(429):
        print("El límite de peticiones está activo.")
    else:
        print("Ninguna petición recibió 429: revise limit_req en perimetro/nginx.conf.")