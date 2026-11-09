import os
from azure.storage.blob import BlobServiceClient

# 1. Conexión con el cliente de Azure
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(connection_string)

CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "bench-contenedor")
PUBLIC_ENDPOINT = os.getenv("AZURE_PUBLIC_ENDPOINT", "http://localhost:10000/devstoreaccount1")

# Asegurar que el contenedor existe
try:
    container_client = blob_service_client.create_container(CONTAINER_NAME)
except Exception:
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)


def subir(nombre_archivo: str, datos: bytes) -> str:
    """Sube un archivo al contenedor de Azure Blob Storage."""
    blob_client = container_client.get_blob_client(nombre_archivo)
    blob_client.upload_blob(datos, overwrite=True)
    return url(nombre_archivo)


def url(nombre_archivo: str) -> str:
    """Devuelve la URL pública para acceder al archivo desde fuera de Docker."""
    return f"{PUBLIC_ENDPOINT}/{CONTAINER_NAME}/{nombre_archivo}"


def eliminar(nombre_archivo: str) -> None:
    """Elimina el archivo del contenedor."""
    blob_client = container_client.get_blob_client(nombre_archivo)
    blob_client.delete_blob()