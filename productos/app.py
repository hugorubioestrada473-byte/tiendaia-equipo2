"""Microservicio Productos de TiendaIA (Laboratorio 2).
Expone un CRUD de productos (nombre, precio, categoría) con FastAPI y guarda los
datos en MongoDB, una base de datos de documentos (cada producto es un JSON).
No llama a otros servicios: Ventas lo consulta por HTTP para obtener el precio y
validar que el producto exista; el API Gateway le reenvía las peticiones externas.
"""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient, ReturnDocument

# ---------------------------------------------------------------- Base de datos
# MONGO_URL llega por variable de entorno (p. ej. mongodb://mongo:27017, donde
# "mongo" es el nombre del contenedor en docker-compose.yml).
# ["tienda"] selecciona la base de datos; MongoDB la crea al primer uso.
db = MongoClient(os.environ["MONGO_URL"])["tienda"]
app = FastAPI(title="TiendaIA - Productos")

# ---------------------------------------------------------------- Modelo de entrada
class ProductoIn(BaseModel):
    """Datos de un producto enviados en el cuerpo JSON.
    Si no cumplen las reglas, FastAPI responde 422 automáticamente.
    """
    nombre: str = Field(min_length=1, max_length=100)
    # Field(gt=0): "greater than 0", el precio debe ser estrictamente positivo
    precio: float = Field(gt=0)
    categoria: str = "general" # valor por omisión si no se envía

def siguiente_id() -> int:
    """Id entero autoincremental (MongoDB no lo tiene: usamos un contador)."""
    # Documento contador {"_id": "productos", "valor": N} en la colección
    # "contadores". $inc suma 1 de forma ATÓMICA en el servidor: aunque lleguen
    # dos peticiones al mismo tiempo, nunca reciben el mismo id.
    # upsert=True crea el contador la primera vez; ReturnDocument.AFTER devuelve
    # el documento ya incrementado.
    doc = db.contadores.find_one_and_update(
        {"_id": "productos"}, {"$inc": {"valor": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return doc["valor"]

# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Verificación de salud usada por el gateway; responde 200."""
    return {"servicio": "productos", "status": "ok"}

@app.get("/productos")
def listar():
    """Devuelve todos los productos (200)."""
    # {"_id": 0} es una proyección: excluye el campo _id interno de MongoDB
    productos = list(db.productos.find({}, {"_id": 0}))
    return productos

@app.post("/productos", status_code=201)
def crear_producto(producto: ProductoIn):
    """Crea un nuevo producto asignándole un ID autoincremental."""
    existente = db.productos.find_one({"nombre": producto.nombre})
    if existente:
        existente.pop("_id", None)
        return existente

    nuevo_id = siguiente_id()
    doc = producto.model_dump() # Si usas pydantic v1, usa producto.dict()
    doc["id"] = nuevo_id
    
    db.productos.insert_one(doc)
    doc.pop("_id", None)
    return doc
@app.get("/productos/{producto_id}")
def obtener_producto_por_id(producto_id: int):
    """Busca un producto específico por su ID (necesario para que Ventas lo valide)."""
    producto = db.productos.find_one({"id": producto_id}, {"_id": 0})
    if not producto:
        raise HTTPException(status_code=404, detail="El producto no existe")
    return producto