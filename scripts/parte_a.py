import time
import requests # librería para hacer peticiones HTTP
t = time.perf_counter() # marca de tiempo inicial
# GET con parámetros: requests arma la URL ?latitude=...&longitude=...
r = requests.get("https://api.open-meteo.com/v1/forecast",
params={"latitude": 21.98, "longitude": -99.01,
        "current": "temperature_2m"},
timeout=10) # nunca esperar para siempre
ms = (time.perf_counter() - t) * 1000 # tiempo de respuesta en milisegundos
print(r.status_code, f"{ms:.0f} ms", len(r.content), "bytes") # código, tiempo y tamaño
print(r.json()["current"]) # el cuerpo JSON convertido a diccionario