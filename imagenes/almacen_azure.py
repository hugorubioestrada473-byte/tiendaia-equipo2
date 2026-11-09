import os
from datetime import datetime, timedelta, timezone
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions
)

class AlmacenAzure:
    def __init__(self):
        """Crea el cliente BlobServiceClient y el contenedor si no existe."""
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_CONTAINER_NAME", "bench-contenedor")
        self.public_endpoint = os.getenv(
            "AZURE_PUBLIC_ENDPOINT", 
            "http://localhost:10000/devstoreaccount1"
        )
        
        # Crear cliente principal
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )
        
        # Obtener o crear el contenedor (container)
        self.container_client = self.blob_service_client.get_container_client(
            self.container_name
        )
        try:
            self.container_client.create_container()
        except Exception:
            pass  # El contenedor ya existe

    def subir(self, clave: str, datos: bytes, tipo: str, metadatos: dict) -> str:
        """Sube un archivo usando upload_blob con ContentSettings y metadata."""
        blob_client = self.container_client.get_blob_client(clave)
        
        # Configurar tipo de contenido y metadatos
        content_settings = ContentSettings(content_type=tipo)
        
        blob_client.upload_blob(
            datos, 
            overwrite=True, 
            content_settings=content_settings, 
            metadata=metadatos
        )
        return self.url(clave)

    def url(self, clave: str, expiracion_segundos: int = 3600) -> str:
        """Genera una URL firmada con SAS (Shared Access Signature)."""
        # Extraer credenciales para generar la SAS
        account_name = self.blob_service_client.account_name
        account_key = self.blob_service_client.credential.account_key
        
        # Generar firma SAS con permiso de lectura y expiración en segundos
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.container_name,
            blob_name=clave,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expiracion_segundos)
        )
        
        # Armar URL: pública + contenedor + clave + ? + SAS
        return f"{self.public_endpoint}/{self.container_name}/{clave}?{sas_token}"

    def eliminar(self, clave: str) -> None:
        """Elimina el blob ignorando si ya no existe."""
        blob_client = self.container_client.get_blob_client(clave)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass  # Si el archivo no existe, se ignora el error igual que en S3