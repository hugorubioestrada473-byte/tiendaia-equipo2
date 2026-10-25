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

client = MongoClient("mongodb://mongo:27017/")
db = client["tienda"]  # <--- Aquí se define 'db'

# Crear índice único para evitar duplicados en el campo deseado (ej. 'nombre' o 'codigo')
db.productos.create_index("nombre", unique=True)

def siguiente_id() -> int:
    doc = db.contadores.find_one_and_update(
        {"_id": "productos"},
        {"$inc": {"valor": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return doc["valor"]

# ---------------------------------------------------------------- Base de datos
# MONGO_URL llega por variable de entorno (p. ej. mongodb://mongo:27017, donde
# "mongo" es el nombre del contenedor en docker-compose.yml).
# ["tienda"] selecciona la base de datos; MongoDB la crea al primer uso.
db=MongoClient(os.environ["MONGO_URL"])["tienda"]

db.productos.create_index("id", unique=True)
app = FastAPI(title="TiendaIA - productos")

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
def listar(categoria: str | None = None, precio_max: float | None = None):
    """Devuelve todos los productos (200)."""
    # {"_id": 0} es una proyección: excluye el campo _id interno de MongoDB
    filtro = {}
    if categoria is not None:
        filtro["categoria"] = categoria
    if precio_max is not None:
        filtro["precio"] = {"$lte": precio_max}   