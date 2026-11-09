"""Genera clientes, productos y ventas sintéticas a través del API Gateway.
Se usa desde el Laboratorio 2 para poblar TiendaIA con datos de prueba.
Todas las peticiones pasan por el gateway (/api/...), igual que un cliente real.
La demanda depende del producto, del mes (temporada) y del precio:
el modelo de IA debe descubrir ese patrón.
Uso: python scripts/generar_carga.py [URL_GATEWAY] [NUM_VENTAS]
"""
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

existentes = {
    p["nombre"]
    for p in sesion.get(f"{GW}/api/productos", timeout=TIEMPO_ESPERA).json()
}

for nombre, (precio, _) in catalogo.items():
    if nombre not in existentes:  # solo se crean los productos que faltan
        sesion.post(
            f"{GW}/api/productos",
            timeout=TIEMPO_ESPERA,
            json={"nombre": nombre, "precio": precio},
        )

clientes = sesion.get(f"{GW}/api/clientes", timeout=TIEMPO_ESPERA).json()
productos = [
    p
    for p in sesion.get(f"{GW}/api/productos", timeout=TIEMPO_ESPERA).json()
    if p["nombre"] in catalogo
]

base = {p["id"]: catalogo[p["nombre"]][1] for p in productos}  # id -> demanda base
temporada = {12: 1.8, 11: 1.4, 1: 1.2, 7: 1.3}  # diciembre vende más

# ---------------------------------------------------------------- Ventas
errores = 0
for _ in range(N):
    p = random.choice(productos)
    mes = random.randint(1, 12)
    # cantidad = demanda base x factor de temporada + ruido normal (gauss)
    cantidad = max(
        1,
        round(base[p["id"]] * temporada.get(mes, 1.0) + random.gauss(0, 1.5)),
    )
    r = sesion.post(
        f"{GW}/api/ventas",
        timeout=TIEMPO_ESPERA,
        json={
            "cliente_id": random.choice(clientes)["id"],
            "producto_id": p["id"],
            "cantidad": cantidad,
            "fecha": date(2025, mes, random.randint(1, 28)).isoformat(),
        },
    )
    errores += r.status_code != 201  # 201 Created = la venta se registró

print(
    f"clientes={len(clientes)} productos={len(productos)} "
    f"ventas={N - errores} errores={errores}"
)