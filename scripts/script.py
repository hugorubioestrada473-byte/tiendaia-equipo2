import requests

# Lista de ciudades a probar
ciudades = [
    "Ciudad Valles", "Real de Catorce", "Monterrey", "Mérida",
    "Tijuana", "Guadalajara", "Cancún", "Puebla",
    "Toluca", "San Luis Potosí"
]

# Endpoint local
url = "http://localhost:8000/recomendacion"

# Hacer las peticiones POST
for ciudad in ciudades:
    r = requests.post(url, json={"ciudad": ciudad})
    print(f"Respuesta para {ciudad}:")
    print(r.json())
    print("-" * 40)

# Consultar historial
historial_url = "http://localhost:8000/historial?limite=10"
r_historial = requests.get(historial_url)
print("Historial de las últimas 10 recomendaciones:")
print(r_historial.json())