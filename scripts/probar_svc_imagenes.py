"""Lab. 6, Parte D: qué puede y qué no puede hacer la identidad svc-imagenes.
Uso (dentro de la red, con las variables del contenedor imagenes):
docker compose exec -T imagenes python - < scripts/probar_svc_imagenes.py
"""
import os
import boto3 # SDK de AWS: cliente de la API S3
from botocore.exceptions import ClientError # error que responde el servidor S3
s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT", "http://seaweedfs:8333"),
                  aws_access_key_id="svc-imagenes",
                  aws_secret_access_key=os.environ["S3_SECRET_KEY"],
                  region_name="us-east-1")
def intentar(nombre, operacion, **argumentos):
    """Ejecuta una operación S3 e imprime si se permitió o se negó."""
    try:
        operacion(**argumentos)
        print(f"{nombre:35} PERMITIDO")
    except ClientError as e:
        print(f"{nombre:35} DENEGADO ({e.response['Error']['Code']})")
B, R = "tiendaia-imagenes", "tiendaia-respaldos"
intentar("subir a su bucket", s3.put_object, Bucket=B, Key="prueba.txt", Body=b"hola")
intentar("leer de su bucket", s3.get_object, Bucket=B, Key="prueba.txt")
intentar("borrar en su bucket", s3.delete_object, Bucket=B, Key="prueba.txt")
intentar("escribir en respaldos", s3.put_object, Bucket=R, Key="x.txt", Body=b"x")
intentar("crear un bucket", s3.create_bucket, Bucket="bucket-intruso")
print("buckets visibles:", [b["Name"] for b in s3.list_buckets()["Buckets"]])