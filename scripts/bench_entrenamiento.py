"""Mide cuánto cuesta entrenar e inferir el modelo del IA-Service (Laboratorio 5).
Entrena el MISMO modelo que ia_service/app.py (one-hot de producto_id + bosque
aleatorio de 200 árboles) con ventas sintéticas de varios tamaños y con distinto
número de núcleos (n_jobs). Para cada combinación mide el tiempo de entrenamiento,
el de 1000 inferencias, el tamaño del modelo y la memoria del proceso (CSV).
No usa Docker ni el gateway: corre directo en la máquina (laptop o codespace).
Uso: python scripts/bench_entrenamiento.py [--tamanos 1000 10000 50000]
[--njobs 1 2 4] [--salida archivo.csv]

"""
import argparse
import csv
import os
import time
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
try:
    import resource # solo existe en Linux y macOS (no en Windows)
except ImportError:
    resource = None
# ---------------------------------------------------------------- Datos sintéticos
# Mismo patrón que scripts/generar_carga.py: demanda base por producto, más venta
# en temporada (diciembre, noviembre, julio, enero) y algo de ruido.
CATALOGO = {1: (120.0, 8), 2: (35.0, 15), 3: (150.0, 5), 4: (60.0, 12), 5: (90.0, 6)}
TEMPORADA = {12: 1.8, 11: 1.4, 1: 1.2, 7: 1.3}
COLUMNAS = ["producto_id", "mes", "precio"] # las mismas que usa el IA-Service
def generar_ventas(n: int, semilla: int = 42) -> pd.DataFrame:
    """Devuelve un DataFrame con n ventas (producto_id, mes, precio, cantidad).
    Se usa numpy para crear todas las filas de golpe (vectorizado): generar
    50 000 ventas con un ciclo for de Python sería mucho más lento.
    """
    rng = np.random.default_rng(semilla) # semilla fija: datos repetibles
    prod = rng.integers(1, 6, n) # productos 1 a 5
    mes = rng.integers(1, 13, n) # meses 1 a 12
    precio_base = np.array([CATALOGO[p][0] for p in prod])
    demanda = np.array([CATALOGO[p][1] for p in prod])
    factor = np.array([TEMPORADA.get(m, 1.0) for m in mes])
    # El precio varía +-10 % (ofertas) para que la columna precio también cuente
    precio = np.round(precio_base * rng.uniform(0.9, 1.1, n), 2)
    cantidad = np.maximum(1, np.round(demanda * factor + rng.normal(0, 1.5, n)))
    return pd.DataFrame({"producto_id": prod, "mes": mes,
    "precio": precio, "cantidad": cantidad})

def crear_modelo(n_jobs: int):
    """Mismo pipeline que ia_service/app.py, con n_jobs procesos para los árboles.
    n_jobs = número de árboles que se construyen en paralelo (uno por núcleo).
    Con n_jobs=1 se usa un solo núcleo aunque la máquina tenga más.
    """
    return make_pipeline(
        ColumnTransformer(
            [("prod", OneHotEncoder(handle_unknown="ignore"), ["producto_id"])],
            remainder="passthrough"),
        RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=n_jobs))
def memoria_proceso_mb() -> float:
    """Memoria RAM que ocupa ahora este proceso (MB); -1 si no se puede medir.
    En Linux (codespace) se lee /proc/self/statm: el 2o. número son las páginas
    de memoria residente (RSS). En macOS se usa el máximo que reporta resource.
    """
    try:
        with open("/proc/self/statm") as f:
            paginas = int(f.read().split()[1])
        return paginas * os.sysconf("SC_PAGE_SIZE") / 1024 ** 2
    except (OSError, ValueError, AttributeError):
        if resource is None: # Windows: no hay forma sencilla
            return -1.0
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2
def tamano_modelo_mb(modelo) -> float:
    """Memoria que ocupan los 200 árboles (MB), sin escribir el modelo a disco.
    Cada árbol guarda sus nodos en arreglos de numpy; se multiplica el total de
    nodos por los bytes de cada nodo. Es casi lo mismo que pesaría el .joblib.
    """
    bosque = modelo[-1].estimators_ # último paso del pipeline: el bosque
    estado = bosque[0].tree_.__getstate__() # arreglos internos de un árbol
    por_nodo = (estado["nodes"].nbytes + estado["values"].nbytes) / estado["node_count"]
    nodos = sum(arbol.tree_.node_count for arbol in bosque)
    return nodos * por_nodo / 1024 ** 2
def medir(n: int, n_jobs: int) -> dict:
    """Entrena con n ventas y n_jobs núcleos; devuelve una fila de resultados."""
    df = generar_ventas(n)
    X, y = df[COLUMNAS], df["cantidad"]
    modelo = crear_modelo(n_jobs)
    # --- Entrenamiento (trabajo por lotes: intensivo en CPU, sin usuario esperando)
    inicio = time.perf_counter() # reloj de alta resolución
    modelo.fit(X, y)
    t_entrenar = time.perf_counter() - inicio
    # --- Inferencia (servicio: importa la latencia de cada petición)
    consultas = generar_ventas(1000, semilla=7)[COLUMNAS]
    inicio = time.perf_counter()
    modelo.predict(consultas) # 1000 inferencias en un solo lote
    t_lote = time.perf_counter() - inicio
    inicio = time.perf_counter()
    for i in range(20): # 20 peticiones de UNA fila cada una
        modelo.predict(consultas.iloc[[i]]) # así llega /ia/predict: fila por fila
    lat_una = (time.perf_counter() - inicio) / 20 * 1000
    
    return {"filas": n, "n_jobs": n_jobs, "nucleos_maquina": os.cpu_count(),
    "entrenar_s": round(t_entrenar, 2),
    "inferir_1000_lote_s": round(t_lote, 3),
    "latencia_1_fila_ms": round(lat_una, 1),
    "modelo_mb": round(tamano_modelo_mb(modelo), 1),
    "memoria_proceso_mb": round(memoria_proceso_mb(), 1)}

# ---------------------------------------------------------------- Programa principal
if __name__ == "__main__":
    nucleos = os.cpu_count()
    p = argparse.ArgumentParser(description="Benchmark de entrenamiento e inferencia")
    p.add_argument("--tamanos", type=int, nargs="+", default=[1000, 10000, 50000])
    p.add_argument("--njobs", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--salida", default=f"bench_entrenamiento_{nucleos}nucleos.csv")
    args = p.parse_args()
    print(f"Máquina con {nucleos} núcleos. Puede tardar varios minutos...")
    filas = []
    for n in args.tamanos:
        for nj in args.njobs:
            fila = medir(n, nj)
            filas.append(fila)
            print(f"filas={n:>6} n_jobs={nj} entrenar={fila['entrenar_s']:>7} s "
                  f"1000 inferencias={fila['inferir_1000_lote_s']} s "
                  f"1 fila={fila['latencia_1_fila_ms']} ms "
                  f"modelo={fila['modelo_mb']} MB "
                  f"proceso={fila['memoria_proceso_mb']} MB", flush=True)
                    # DictWriter escribe el encabezado con las llaves del diccionario y una fila
                    # por medición: el CSV se abre directo en una hoja de cálculo.
    with open(args.salida, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"Resultados guardados en {args.salida}")