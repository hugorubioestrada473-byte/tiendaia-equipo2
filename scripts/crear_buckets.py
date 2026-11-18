"""Crea los buckets con la identidad de ADMINISTRADOR (los servicios no pueden: Lab. 6).
Mínimo privilegio: las llaves de los microservicios solo leen y escriben objetos;
crear buckets es tarea del administrador, por eso se hace con este script aparte.
Uso: S3_ENDPOINT=http://localhost:8333 S3_ACCESS_KEY=admin S3_SECRET_KEY=... \
python scripts/crear_buckets.py tiendaia-imagenes tiendaia-respaldos
"""
import os
import sys
import boto3 # SDK de AWS para Python: cliente del API S3
# endpoint_url permite usar un servidor S3 propio (SeaweedFS); si falta, Amazon S3
s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT"),
                    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                    region_name=os.getenv("S3_REGION", "us-east-1"))

# Se consultan los buckets existentes para que el script se pueda repetir sin error
existentes = {b["Name"] for b in s3.list_buckets()["Buckets"]}
for nombre in sys.argv[1:]: # un bucket por cada argumento
    if nombre in existentes:
        print("ya existe:", nombre)
    else:
        s3.create_bucket(Bucket=nombre)
        print("creado:", nombre)