"""Genera carga sostenida contra el IA-Service dentro de Kubernetes (Laboratorio 5).
Se ejecuta DENTRO del clúster (en un pod con la misma imagen tiendaia-ia:1), así
la carga no pasa por "kubectl port-forward", que tiene un solo túnel y sería el
cuello de botella. Varios hilos piden /ia/predict sin parar durante el tiempo
indicado; cada 15 s se imprime cuántas peticiones hubo, cuántas fallaron y la
latencia media y p95. Con esa carga el HPA debe agregar réplicas.
Uso (desde el pod): python - [URL] [SEGUNDOS] [HILOS] < carga_k8s.py
Ejemplo: python - http://ia:8000 180 8 < scripts/carga_k8s.py
"""
import random
import statistics
import sys
import threading
import time
import requests

# ---------------------------------------------------------------- Configuración
# "ia" es el nombre del Service de Kubernetes: su DNS interno reparte las
# peticiones entre todas las réplicas (pods) que estén listas.
URL = sys.argv[1] if len(sys.argv) > 1 else "http://ia:8000"
DURACION = int(sys.argv[2]) if len(sys.argv) > 2 else 180 # segundos de carga
HILOS = int(sys.argv[3]) if len(sys.argv) > 3 else 8 # clientes simultáneos
INTERVALO = 15 # cada cuántos segundos se imprime un resumen
TIEMPO_ESPERA = 10 # segundos máximos por petición
latencias = [] # ms de cada petición exitosa del intervalo
errores = 0 # peticiones fallidas del intervalo
candado = threading.Lock() # evita que dos hilos modifiquen las listas a la vez
fin = time.time() + DURACION


def trabajador():
    """Un cliente: repite GET /ia/predict con datos al azar hasta que acaba el tiempo."""
    global errores
    # Cada hilo tiene su propia sesión. Ojo: una sesión reutiliza la conexión y
    # el Service reparte por CONEXIÓN, por eso se usan varios hilos (varias
    # conexiones) para que la carga llegue a todas las réplicas.
    sesion = requests.Session()
    while time.time() < fin:
        params = {
            "producto_id": random.randint(1, 5),
            "mes": random.randint(1, 12),
            "precio": random.choice([35, 60, 90, 120, 150]),
        }
        inicio = time.perf_counter()
        try:
            r = sesion.get(f"{URL}/ia/predict", params=params, timeout=TIEMPO_ESPERA)
            ok = r.status_code == 200
        except requests.RequestException: # tiempo agotado, conexión rechazada...
            ok = False
        ms = (time.perf_counter() - inicio) * 1000
        with candado: # sección crítica: un hilo a la vez
            if ok:
                latencias.append(ms)
            else:
                errores += 1


# ---------------------------------------------------------------- Programa principal
if __name__ == "__main__":
    print(f"Carga contra {URL}: {HILOS} hilos durante {DURACION} s", flush=True)
    hilos = [threading.Thread(target=trabajador, daemon=True) for _ in range(HILOS)]
    for h in hilos:
        h.start()
    t0 = anterior = time.time()
    print(" t(s) peticiones errores peticiones/s media(ms) p95(ms)", flush=True)
    while time.time() < fin:
        time.sleep(min(INTERVALO, fin - time.time() + 0.5)) # sin pasarse del final
        ahora = time.time()
        segundos, anterior = ahora - anterior, ahora # duración real del intervalo
        with candado: # se toman los datos y se reinician
            datos, fallas = sorted(latencias), errores
            latencias.clear()
            errores = 0
        if datos:
            media = statistics.mean(datos)
            p95 = datos[int(0.95 * len(datos)) - 1] if len(datos) > 1 else datos[0]
        else:
            media = p95 = 0.0
        print(
            f"{ahora - t0:6.0f} {len(datos):10d} {fallas:7d} "
            f"{len(datos) / segundos:12.1f} {media:9.1f} {p95:7.1f}",
            flush=True,
        )
    for h in hilos:
        h.join(timeout=TIEMPO_ESPERA)
    print("Carga terminada. Observe cómo el HPA reduce las réplicas en unos minutos.")