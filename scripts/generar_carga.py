import os
import random
import sys
from datetime import date
import requests  # cliente HTTP para llamar al gateway

# ---------------------------------------------------------------- Configuración
GW = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
random.seed(42)  # semilla fija: cada ejecución genera los mismos datos
TOKEN = os.getenv("TOKEN")  # desde el Lab. 6: JWT de admin
TIEMPO_ESPERA = 10  # segundos: nunca esperar para siempre al gateway
sesion = requests.Session()  # reutiliza conexiones TCP entre peticiones (más rápido)

if TOKEN:
    # Las cabeceras de la sesión se envían en TODAS las peticiones
    sesion.headers.update({"Authorization": f"Bearer {TOKEN}"})

# ---------------------------------------------------------------- Clientes y productos
for i in range(1, 11):  # 409 si ya existe: no es error
    sesion.post(
        f"{GW}/api/clientes",
        timeout=TIEMPO_ESPERA,
        json={"nombre": f"Cliente {i}", "correo": f"cliente{i}@ejemplo.com"},
    )

# nombre -> (precio, demanda base mensual)
catalogo = {
    "Café de la Huasteca": (120.0, 8),
    "Piloncillo": (35.0, 15),
    "Miel de abeja": (150.0, 5),
    "Zacahuil (porción)": (60.0, 12),
    "Bocoles (docena)": (90.0, 6),
}

# 1. Obtenemos los productos actuales de forma segura
respuesta = sesion.get(f"{GW}/api/productos", timeout=TIEMPO_ESPERA)
datos = respuesta.json()
if datos is None:
    datos = []
existentes = {p["nombre"] for p in datos}

# 2. Creamos los productos que falten y revisamos qué responde el servidor
for nombre, (precio, _) in catalogo.items():
    if nombre not in existentes:
        r = sesion.post(
            f"{GW}/api/productos",
            timeout=TIEMPO_ESPERA,
            json={"nombre": nombre, "precio": precio},
        )
        print(f"Creando '{nombre}' -> Status: {r.status_code}, Respuesta: {r.text}")

# 3. Obtenemos la lista definitiva de clientes protegiéndonos contra 'null'
res_clientes = sesion.get(f"{GW}/api/clientes", timeout=TIEMPO_ESPERA).json()
clientes = res_clientes if res_clientes is not None else []

# 4. Obtenemos la lista definitiva de productos con sus IDs reales
res_productos = sesion.get(f"{GW}/api/productos", timeout=TIEMPO_ESPERA)
productos = res_productos.json()
if productos is None:
    productos = []

# Mapeo de ID de producto a su demanda base
base = {
    p["id"]: catalogo[p["nombre"]][1] 
    for p in productos 
    if p["nombre"] in catalogo
}
temporada = {12: 1.8, 11: 1.4, 1: 1.2, 7: 1.3}  # diciembre vende más

# Inspeccionemos qué productos está viendo el script justo antes de vender
print("Productos detectados por el script:", productos)
# ---------------------------------------------------------------- Ventas
# ---------------------------------------------------------------- Ventas
errores = 0
if productos and clientes:
    for _ in range(N):
        p = random.choice(productos)
        mes = random.randint(1, 12)
        demanda_base = base.get(p["id"], 5)
        cantidad = max(
            1,
            round(demanda_base * temporada.get(mes, 1.0) + random.gauss(0, 1.5)),
        )
        payload = {
            "cliente_id": random.choice(clientes)["id"],
            "producto_id": p["id"],
            "cantidad": cantidad,
            "fecha": date(2025, mes, random.randint(1, 28)).isoformat(),
        }
        r = sesion.post(
            f"{GW}/api/ventas",
            timeout=TIEMPO_ESPERA,
            json=payload,
        )
        
        # Imprimir el error de la primera venta fallida para diagnosticar
        if r.status_code != 201 and errores == 0:
            print(f"DEBUG Error en venta -> Status: {r.status_code}, Respuesta: {r.text}, Payload enviado: {payload}")

        errores += r.status_code != 201
else:
    print("Aviso: No hay productos o clientes disponibles para registrar ventas.")