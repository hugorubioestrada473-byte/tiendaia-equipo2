"""Microservicio Imágenes de TiendaIA (Laboratorio 4).
Guarda las fotos de los productos en un almacenamiento de objetos con API S3
(SeaweedFS en el laboratorio) y entrega URL prefirmadas para descargarlas.
Consulta y actualiza al microservicio Productos por HTTP con requests; la
lógica de S3 vive en almacen.py.
"""
import hashlib  # huella SHA-256 para verificar la integridad del archivo
import os
import uuid  # nombres únicos: dos fotos nunca se sobrescriben entre sí

import requests  # cliente HTTP para llamar al microservicio Productos
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from almacen import AlmacenS3  # adaptador S3 (subir, url, eliminar)

# ---------------------------------------------------------------- Configuración
PRODUCTOS_URL = os.getenv("PRODUCTOS_URL", "http://productos:8000")
# Tipos MIME aceptados -> extensión del archivo que se guarda en el bucket
TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB: límite para no llenar el almacenamiento
EXPIRA_S = 3600  # validez de la URL prefirmada (1 hora)

almacen = AlmacenS3()  # al arrancar se conecta a S3 y revisa el bucket
TIEMPO_ESPERA = 5  # segundos máximos de espera a Productos
sesion = requests.Session()  # reutiliza conexiones TCP con Productos

app = FastAPI(title="TiendaIA - Imágenes")


# ---------------------------------------------------------------- Subir imagen
@app.post("/imagenes", status_code=201)
async def subir(producto_id: int = Form(gt=0), archivo: UploadFile = File(...)):
    """Recibe un formulario multipart (producto_id + archivo) y guarda la imagen.
    Responde 201 con la clave del objeto; 404 si el producto no existe, 415 si
    el tipo no es imagen permitida, 413 si pasa de 5 MB y 422 si producto_id
    no es un entero mayor que cero (Form(gt=0) lo valida FastAPI).
    """
    p = producto(producto_id)  # 404 aquí si el producto no existe
    if archivo.content_type not in TIPOS:  # 415 = tipo de contenido no soportado
        raise HTTPException(415, "Solo se aceptan JPEG, PNG o WebP")
    datos = await archivo.read()  # bytes completos del archivo subido
    if len(datos) > MAX_BYTES:  # 413 = la carga es demasiado grande
        raise HTTPException(413, "La imagen excede 5 MB")

    # Clave = "ruta" del objeto dentro del bucket. S3 no tiene carpetas reales:
    # el prefijo productos/<id>/ solo agrupa las claves de cada producto.
    clave = f"productos/{producto_id}/{uuid.uuid4().hex}.{TIPOS[archivo.content_type]}"
    sha = hashlib.sha256(datos).hexdigest()  # huella para comprobar integridad

    # Los metadatos viajan junto al objeto en S3 (cabeceras x-amz-meta-*)
    almacen.subir(clave, datos, archivo.content_type, {"sha256": sha})
    if p.get("imagen_key"):  # reemplazo: borrar la anterior
        almacen.eliminar(p["imagen_key"])
    asociar(producto_id, clave)  # Productos guarda solo la clave
    return {"producto_id": producto_id, "clave": clave,
            "bytes": len(datos), "sha256": sha}


# ---------------------------------------------------------------- Obtener URL
@app.get("/imagenes/{producto_id}")
def obtener(producto_id: int):
    """Devuelve una URL prefirmada (1 hora) para descargar la imagen del producto."""
    clave = producto(producto_id).get("imagen_key")  # .get: puede no existir
    if not clave:
        raise HTTPException(404, "El producto no tiene imagen")
    return {"producto_id": producto_id,
            "url": almacen.url(clave, EXPIRA_S),
            "expira_en_s": EXPIRA_S}


# ---------------------------------------------------------------- Borrar imagen
@app.delete("/imagenes/{producto_id}", status_code=204)
def eliminar(producto_id: int):
    """Borra el objeto en S3 y quita la clave del producto (204 o 404)."""
    clave = producto(producto_id).get("imagen_key")
    if not clave:
        raise HTTPException(404, "El producto no tiene imagen")
    almacen.eliminar(clave)  # primero el objeto
    asociar(producto_id, None)  # luego la asociación


# ---------------------------------------------------------------- Salud
@app.get("/health")
def salud():
    """Lo consulta el gateway; sin este endpoint marca el servicio como caído."""
    return {"servicio": "imagenes", "status": "ok", "bucket": almacen.bucket}


# ---------------------------------------------------------------- Auxiliares
def producto(pid: int) -> dict:
    """Consulta el producto en Productos; 404 si no existe."""
    r = sesion.get(f"{PRODUCTOS_URL}/productos/{pid}", timeout=TIEMPO_ESPERA)
    if r.status_code == 404:
        raise HTTPException(404, "Producto no encontrado")
    r.raise_for_status()
    return r.json()


def asociar(pid: int, clave: str | None):
    """Guarda la clave del objeto en Productos (None = producto sin imagen)."""
    r = sesion.put(f"{PRODUCTOS_URL}/productos/{pid}/imagen",
        json={"imagen_key": clave}, timeout=TIEMPO_ESPERA)
    r.raise_for_status()