"""Laboratorio 4: capacidad, velocidad y confiabilidad del almacenamiento de objetos.
Sube y baja archivos grandes (MB/s), muchos archivos pequeños (latencia por
archivo) y verifica la integridad con SHA-256. Sirve igual para SeaweedFS,
Supabase Storage, Backblaze B2 o Amazon S3 porque todos hablan el mismo API S3.
Uso:
DESTINO=seaweedfs S3_ENDPOINT=http://localhost:8333 \
S3_ACCESS_KEY=... S3_SECRET_KEY=... \
BUCKET=bench-equipo python scripts/bench_almacenamiento.py
Para Amazon S3 omita S3_ENDPOINT.
Los resultados se agregan a resultados_almacenamiento.csv
"""
import csv
import hashlib
import os
import statistics as st
import time
from datetime import datetime
import boto3  # SDK de AWS para Python: cliente del API S3

# ---------------------------------------------------------------- Configuración
DESTINO = os.getenv("DESTINO", "sin-nombre")  # etiqueta para la tabla de resultados
BUCKET = os.environ["BUCKET"]
# endpoint_url permite usar un servidor S3 propio; si falta, se usa Amazon S3
s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT"),
                  aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                  aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                  region_name=os.getenv("S3_REGION", "us-east-1"))

try:
    s3.head_bucket(Bucket=BUCKET)  # ¿existe el bucket y hay permiso? (sin descargar)
except Exception:
    s3.create_bucket(Bucket=BUCKET)

filas = []


def registrar(prueba, valores, unidad, errores=0):
    """Calcula media y desviación estándar de una prueba, la imprime y la guarda."""
    fila = {"fecha": datetime.now().isoformat(timespec="seconds"), "destino": DESTINO,
            "prueba": prueba, "media": round(st.mean(valores), 2),
            "desv": round(st.stdev(valores), 2) if len(valores) > 1 else 0,
            "unidad": unidad, "n": len(valores), "errores": errores}
    filas.append(fila)
    print(f"{DESTINO:>8} | {prueba:<22} {fila['media']:>9} ± {fila['desv']:<7} "
          f"{unidad} errores={errores}")


def archivos_grandes(mb, reps=5):
    """Mide velocidad de subida y bajada (MB/s) de un archivo de mb megabytes."""
    datos = os.urandom(mb * 1024 * 1024)  # bytes aleatorios: no se pueden comprimir
    h = hashlib.sha256(datos).hexdigest()  # huella para comprobar la integridad
    sub, baj, err = [], [], 0
    for i in range(reps):
        k = f"bench/{mb}MB-{i}"  # clave (nombre) del objeto en el bucket
        t = time.perf_counter()
        s3.put_object(Bucket=BUCKET, Key=k, Body=datos)
        sub.append(mb / (time.perf_counter() - t))
        t = time.perf_counter()
        leido = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()
        baj.append(mb / (time.perf_counter() - t))
        err += hashlib.sha256(leido).hexdigest() != h  # integridad
        s3.delete_object(Bucket=BUCKET, Key=k)
    registrar(f"subida {mb} MB", sub, "MB/s", err)
    registrar(f"bajada {mb} MB", baj, "MB/s", err)


def archivos_pequenos(n=200, kb=10):
    """Sube n archivos de kb KB: mide latencia por archivo y archivos por segundo."""
    datos, lat, err = os.urandom(kb * 1024), [], 0
    t0 = time.perf_counter()
    for i in range(n):
        t = time.perf_counter()
        try:
            s3.put_object(Bucket=BUCKET, Key=f"bench/peq-{i}", Body=datos)
        except Exception:  # se cuenta el fallo y se sigue midiendo
            err += 1
        lat.append((time.perf_counter() - t) * 1000)
    total = time.perf_counter() - t0
    registrar(f"{n} archivos de {kb} KB", lat, "ms/archivo", err)
    registrar("rendimiento pequeños", [n / total], "archivos/s")
    for i in range(n):  # limpieza: no dejar basura en el bucket
        s3.delete_object(Bucket=BUCKET, Key=f"bench/peq-{i}")


# ---------------------------------------------------------------- Ejecución
# 25 MB: debajo del límite por archivo de varios planes gratuitos
for mb in (1, 10, 25):
    archivos_grandes(mb)
archivos_pequenos()

# Se agrega al CSV (modo "a"); el encabezado solo se escribe si el archivo es nuevo
nuevo = not os.path.exists("resultados_almacenamiento.csv")
with open("resultados_almacenamiento.csv", "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=filas[0].keys())
    if nuevo:
        w.writeheader()
    w.writerows(filas)