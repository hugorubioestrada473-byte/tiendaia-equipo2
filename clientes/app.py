"""Microservicio Clientes de TiendaIA (Laboratorio 2).
Expone un CRUD (crear, leer, actualizar, borrar) de clientes mediante una API REST
hecha con FastAPI. Los datos se guardan en MySQL usando SQLAlchemy Core.
No llama a otros servicios: el microservicio Ventas lo consulta por HTTP para
validar que un cliente exista, y el API Gateway le reenvía las peticiones externas.
"""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import (Column, Integer, MetaData, String, Table, create_engine,
                        delete, insert, select, update)
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------- Base de datos
# La URL de conexión llega por variable de entorno (la define docker-compose.yml),
# p. ej. mysql+pymysql://usuario:clave@mysql:3306/tienda. Así el mismo código
# funciona en cualquier máquina sin escribir contraseñas dentro del programa.
# pool_pre_ping=True revisa que la conexión siga viva antes de usarla: evita errores
# si MySQL cerró conexiones inactivas o se reinició.
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

# Descripción de la tabla "clientes" (SQLAlchemy Core, sin ORM).
meta = MetaData()
clientes = Table(
    "clientes", meta,
    # Llave primaria entera que MySQL incrementa sola (1, 2, 3...)
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nombre", String(100), nullable=False),
    # unique=True: la base de datos impide dos clientes con el mismo correo
    Column("correo", String(120), nullable=False, unique=True),
)
meta.create_all(engine) # crea la tabla si no existe

app = FastAPI(title="TiendaIA - Clientes")

# ---------------------------------------------------------------- Modelo de entrada
class ClienteIn(BaseModel):
    """Datos que el usuario envía en el cuerpo JSON para crear o actualizar.
    Pydantic valida automáticamente: si algo no cumple, FastAPI responde 422
    (Unprocessable Entity) sin que se ejecute el código del endpoint.
    """
    # Field(min_length=1, max_length=100): texto no vacío y de máximo 100 letras,
    # igual que la columna String(100) de la tabla.
    nombre: str = Field(min_length=1, max_length=100)
    # pattern: expresión regular sencilla para un correo (algo@algo.algo)
    correo: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)

# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Verificación de salud: el gateway y Docker la usan para saber si está vivo.
    Devuelve 200 con el nombre del servicio.
    """
    return {"servicio": "clientes", "status": "ok"}

@app.get("/clientes")
def listar():
    """Devuelve la lista de todos los clientes (200)."""
    # engine.connect() abre una conexión del pool y la devuelve al salir del with
    with engine.connect() as c:
        # r._mapping permite convertir cada fila en diccionario -> JSON
        return [dict(r._mapping) for r in c.execute(select(clientes))]

@app.get("/clientes/{cliente_id}")
def obtener(cliente_id: int):
    """Devuelve un cliente por su id (200) o 404 si no existe."""
    with engine.connect() as c:
        r = c.execute(select(clientes).where(clientes.c.id == cliente_id)).first()
    if r is None:
        # 404 Not Found: el recurso pedido no existe. Ventas usa esta respuesta
        # para saber que el cliente no es válido.
        raise HTTPException(404, "Cliente no encontrado")
    return dict(r._mapping)

@app.post("/clientes", status_code=201)
def crear(cli: ClienteIn):
    """Crea un cliente y devuelve sus datos con el id asignado.
    Responde 201 (Created) si se creó, 409 si el correo ya existe y
    422 si los datos no pasan la validación de ClienteIn.
    """
    try:
        # engine.begin() abre una transacción: hace COMMIT al salir del with,
        # o ROLLBACK si ocurre una excepción.
        with engine.begin() as c:
            r = c.execute(insert(clientes).values(**cli.model_dump()))
    except IntegrityError:
        # La restricción unique del correo falló. 409 Conflict: la petición es
        # correcta, pero choca con el estado actual de los datos.
        raise HTTPException(409, "El correo ya está registrado")
    # inserted_primary_key contiene el id que MySQL generó para la nueva fila
    return {"id": r.inserted_primary_key[0], **cli.model_dump()}

@app.put("/clientes/{cliente_id}")
def actualizar(cliente_id: int, cli: ClienteIn):
    """Reemplaza nombre y correo de un cliente (200) o responde 404 si no existe."""
    with engine.begin() as c:
        r = c.execute(update(clientes).where(clientes.c.id == cliente_id)
                      .values(**cli.model_dump()))

    # rowcount = número de filas modificadas; 0 significa que el id no existe
    if r.rowcount == 0:
        raise HTTPException(404, "Cliente no encontrado")
    return {"id": cliente_id, **cli.model_dump()}

@app.delete("/clientes/{cliente_id}", status_code=204)
def eliminar(cliente_id: int):
    """Borra un cliente. Responde 204 (sin contenido) o 404 si no existe."""
    with engine.begin() as c:
        r = c.execute(delete(clientes).where(clientes.c.id == cliente_id))
    if r.rowcount == 0:
        raise HTTPException(404, "Cliente no encontrado")
    # Sin return: 204 No Content indica éxito sin cuerpo de respuesta
    