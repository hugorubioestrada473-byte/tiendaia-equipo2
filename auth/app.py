"""Auth-Service de TiendaIA (Laboratorio 6): identidad de personas y de servicios.
- Personas (usuarios): inician sesión con usuario y contraseña y reciben un JWT firmado
(HS256) que incluye sus roles; el API Gateway lo verifica en cada petición.
- Servicios (microservicios): se identifican con una API Key; aquí solo se guarda su
hash SHA-256 y los demás servicios la validan llamando a /auth/validar-clave.
Guarda todo en una base SQLite propia (un archivo en el volumen /data).
"""
import hashlib  # funciones hash: PBKDF2 para contraseñas y SHA-256 para API Keys
import hmac  # compare_digest: comparación en tiempo constante
import os
import secrets  # generador aleatorio criptográficamente seguro (sales y claves)
import sqlite3
import time
import jwt  # librería PyJWT: crea y verifica JSON Web Tokens
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- Configuración
# El secreto que firma los JWT se lee del entorno y NUNCA se escribe en el código:
# quien lo conozca puede fabricar tokens válidos. Si falta, está vacío o es muy
# corto (fácil de adivinar), el servicio NO arranca: es preferible a arrancar inseguro.
JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET falta o es muy corto (mínimo 32 caracteres)")

# check_same_thread=False: FastAPI atiende peticiones en varios hilos y todos
# comparten esta misma conexión a SQLite.
DB = sqlite3.connect(os.getenv("AUTH_DB", "/data/auth.db"), check_same_thread=False)

# Dos tablas: personas (con sal y hash de la contraseña, nunca la contraseña) y
# servicios (con el hash SHA-256 de su API Key, nunca la clave en claro).
DB.executescript("""
CREATE TABLE IF NOT EXISTS usuarios
(usuario TEXT PRIMARY KEY, sal TEXT, hash TEXT, roles TEXT);
CREATE TABLE IF NOT EXISTS servicios
(servicio TEXT PRIMARY KEY, hash_clave TEXT, creado REAL);
""")

# HTTPBearer extrae el token de la cabecera "Authorization: Bearer <token>";
# si la cabecera falta, FastAPI rechaza la petición automáticamente (401 en las
# versiones recientes, 403 en las antiguas) sin ejecutar el endpoint.
app, bearer = FastAPI(title="TiendaIA - Auth"), HTTPBearer()


# ---------------------------------------------------------------- Contraseñas
def hash_contrasena(contrasena: str, sal: str) -> str:
    """Calcula el hash PBKDF2-SHA256 de una contraseña y devuelve su texto hexadecimal.
    Recibe la contraseña y la sal (hexadecimal). PBKDF2 repite el hash 200 000 veces
    a propósito: el inicio de sesión tarda milisegundos, pero probar millones de
    contraseñas por fuerza bruta se vuelve muy costoso para un atacante.
    """
    return hashlib.pbkdf2_hmac(
        "sha256", contrasena.encode(), bytes.fromhex(sal), 200_000
    ).hex()


def crear_usuario(usuario: str, contrasena: str, roles: list[str]):
    """Crea (o reemplaza) un usuario con una sal nueva y sus roles separados por comas.
    La sal aleatoria hace que dos usuarios con la misma contraseña tengan hashes
    distintos, lo que inutiliza las tablas de hashes precalculados.
    """
    sal = secrets.token_hex(16)  # 16 bytes aleatorios = 32 caracteres hex
    DB.execute(
        "INSERT OR REPLACE INTO usuarios VALUES (?,?,?,?)",
        (usuario, sal, hash_contrasena(contrasena, sal), ",".join(roles)),
    )
    DB.commit()


# Administrador inicial: si se define ADMIN_PASSWORD se crea (o actualiza) "admin".
# Sin él no habría nadie con permiso para registrar más usuarios o servicios.
if os.getenv("ADMIN_PASSWORD"):
    crear_usuario("admin", os.environ["ADMIN_PASSWORD"], ["admin"])


# ---------------------------------------------------------------- Autorización
def requiere_admin(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    """Dependencia de FastAPI: exige un JWT válido con el rol "admin".
    Devuelve el contenido (claims) del token. Responde 401 si el token es inválido
    o expiró (la identidad no se pudo comprobar) y 403 si el token es válido pero
    el usuario no es admin (se sabe quién es, pero no tiene permiso).
    """
    try:
        # decode verifica la firma con JWT_SECRET y la fecha de expiración ("exp").
        # Se fija algorithms=["HS256"] para no aceptar tokens con otro algoritmo.
        datos = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Token inválido o expirado")
    if "admin" not in datos["roles"]:
        raise HTTPException(403, "Se requiere rol admin")
    return datos


# ---------------------------------------------------------------- Modelos (Pydantic)
class Login(BaseModel):
    """Cuerpo de /auth/login: credenciales de una persona."""

    usuario: str
    contrasena: str


class UsuarioIn(Login):
    """Cuerpo para registrar un usuario. Si no cumple las reglas, FastAPI responde 422."""

    contrasena: str = Field(min_length=8)  # contraseñas de al menos 8 caracteres
    roles: list[str] = Field(min_length=1)  # al menos un rol: admin, vendedor, analista


class ServicioIn(BaseModel):
    """Cuerpo para registrar un servicio: nombre en minúsculas, dígitos o guiones."""

    servicio: str = Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")


# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Health check: confirma que el servicio está vivo (siempre 200)."""
    return {"servicio": "auth", "status": "ok"}


@app.post("/auth/login")
def login(d: Login):
    """Verifica usuario y contraseña y entrega un JWT válido por 30 minutos.
    Responde 200 con el token o 401 si las credenciales son incorrectas.
    """
    fila = DB.execute(
        "SELECT sal, hash, roles FROM usuarios WHERE usuario=?", (d.usuario,)
    ).fetchone()

    # compare_digest tarda lo mismo aunque los hashes difieran en el primer carácter,
    # así no se filtra información por el tiempo de respuesta. El mensaje es el mismo
    # si falla el usuario o la contraseña, para no revelar qué usuarios existen.
    if not fila or not hmac.compare_digest(
        hash_contrasena(d.contrasena, fila[0]), fila[1]
    ):
        raise HTTPException(401, "Usuario o contraseña incorrectos")

    # Un JWT tiene tres partes: cabecera, contenido (claims) y firma. El contenido
    # NO está cifrado (cualquiera puede leerlo en base64), pero la firma impide
    # modificarlo. "sub" = usuario, "roles" = permisos, "exp" = expira en 30 min.
    token = jwt.encode(
        {
            "sub": d.usuario,
            "roles": fila[2].split(","),
            "exp": int(time.time()) + 30 * 60,
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    return {"access_token": token, "token_type": "bearer", "expira_en_s": 1800}


@app.post("/auth/usuarios", status_code=201)
def registrar_usuario(u: UsuarioIn, _=Depends(requiere_admin)):
    """Registra un usuario con sus roles (solo admin).
    Responde 201 (creado), 401/403 si quien llama no es admin y 422 si los datos
    no cumplen las reglas del modelo.
    """
    crear_usuario(u.usuario, u.contrasena, u.roles)
    return {"usuario": u.usuario, "roles": u.roles}  # nunca se devuelve la contraseña


@app.post("/auth/servicios", status_code=201)
def registrar_servicio(s: ServicioIn, _=Depends(requiere_admin)):
    """Genera una API Key nueva para un microservicio (solo admin).
    Devuelve la clave en claro UNA sola vez; en la base solo queda su hash SHA-256.
    Si se registra de nuevo el mismo servicio, la clave anterior deja de servir.
    Responde 201, 401/403 (no es admin) o 422 (nombre inválido).
    """
    # token_urlsafe(32): 32 bytes aleatorios, imposible de adivinar. El prefijo "tia_"
    # ayuda a reconocer la clave si aparece por error en un log o repositorio.
    clave = "tia_" + secrets.token_urlsafe(32)
    # Se guarda solo el hash: si alguien roba la base de datos no obtiene claves útiles.
    # Basta SHA-256 (sin PBKDF2) porque la clave es larga y aleatoria, no una contraseña.
    DB.execute(
        "INSERT OR REPLACE INTO servicios VALUES (?,?,?)",
        (s.servicio, hashlib.sha256(clave.encode()).hexdigest(), time.time()),
    )
    DB.commit()
    return {
        "servicio": s.servicio,
        "api_key": clave,
        "aviso": "Guárdela ahora: no se puede volver a consultar",
    }


@app.get("/auth/validar-clave")
def validar_clave(x_api_key: str | None = Header(default=None)):
    """Indica qué servicio es dueño de una API Key (cabecera x-api-key).
    Lo usan los microservicios protegidos (ver comun/seguridad.py). Responde 200 con
    el nombre del servicio, 401 si no se envió clave y 403 si la clave no existe.
    """
    if not x_api_key:
        raise HTTPException(401, "API Key requerida")
    # Se calcula el hash de la clave recibida y se busca ese hash en la tabla.
    h = hashlib.sha256(x_api_key.encode()).hexdigest()
    fila = DB.execute(
        "SELECT servicio FROM servicios WHERE hash_clave=?", (h,)
    ).fetchone()

    if not fila:
        raise HTTPException(403, "API Key inválida")
    return {"valida": True, "servicio": fila[0]}