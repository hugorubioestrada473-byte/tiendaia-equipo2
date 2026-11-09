"""Microservicio Productos de TiendaIA (Laboratorio 2 y 4).
CRUD de productos (nombre, precio, categoría) con FastAPI y MongoDB.
Ventas lo consulta por HTTP; el API Gateway le reenvía las peticiones externas.
Laboratorio 4: PUT /productos/{id}/imagen guarda la clave del objeto en S3.
"""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument

# MONGO_URL llega por variable de entorno (mongodb://mongo:27017)
db = MongoClient(os.environ["MONGO_URL"])["tienda"]
db.productos.create_index("id", unique=True)
app = FastAPI(title="TiendaIA - Productos")


class ProductoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    precio: float = Field(gt=0)
    categoria: str = "general"


class ImagenIn(BaseModel):
    imagen_key: str | None  # sin valor por omisión: obligatorio aunque valga null


def siguiente_id() -> int:
    """Id entero autoincremental usando un contador atómico en MongoDB."""
    doc = db.contadores.find_one_and_update(
        {"_id": "productos"}, {"$inc": {"valor": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return doc["valor"]


@app.get("/health")
def salud():
    return {"servicio": "productos", "status": "ok"}


@app.get("/productos")
def listar(categoria: str | None = None, precio_max: float | None = None):
    filtro = {}
    if categoria is not None:
        filtro["categoria"] = categoria
    if precio_max is not None:
        filtro["precio"] = {"$lte": precio_max}
    return list(db.productos.find(filtro, {"_id": 0}))


@app.get("/productos/{producto_id}")
def obtener(producto_id: int):
    p = db.productos.find_one({"id": producto_id}, {"_id": 0})
    if p is None:
        raise HTTPException(404, "Producto no encontrado")
    return p


@app.post("/productos", status_code=201)
def crear(datos: ProductoIn):
    doc = {"id": siguiente_id(), **datos.model_dump()}
    db.productos.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.put("/productos/{producto_id}")
def actualizar(producto_id: int, datos: ProductoIn):
    p = db.productos.find_one_and_update(
        {"id": producto_id}, {"$set": datos.model_dump()},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if p is None:
        raise HTTPException(404, "Producto no encontrado")
    return p


@app.put("/productos/{producto_id}/imagen")
def asignar_imagen(producto_id: int, datos: ImagenIn):
    """Guarda (o borra, con null) la clave de la imagen del producto."""
    r = db.productos.update_one(
        {"id": producto_id}, {"$set": {"imagen_key": datos.imagen_key}})
    if r.matched_count == 0:
        raise HTTPException(404, "Producto no encontrado")
    return {"id": producto_id, "imagen_key": datos.imagen_key}


@app.delete("/productos/{producto_id}", status_code=204)
def borrar(producto_id: int):
    r = db.productos.delete_one({"id": producto_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Producto no encontrado")