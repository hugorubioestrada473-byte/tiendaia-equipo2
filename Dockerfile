# Imagen común para todos los microservicios de TiendaIA.
# Se construye desde la raíz del repositorio:
#   docker build --build-arg SERVICIO=clientes .
# Un solo Dockerfile sirve para todos: el argumento SERVICIO indica qué carpeta
# (clientes, productos, ventas, ia_service, gateway...) se copia a la imagen.

# Imagen base oficial de Python 3.12 en su versión "slim" (más ligera)
FROM python:3.11-slim

# Argumento de construcción: lo pasa docker-compose.yml en build.args
ARG SERVICIO

# Directorio de trabajo dentro del contenedor; los siguientes comandos se ejecutan ahí
WORKDIR /app

# Se copian primero SOLO las dependencias: Docker guarda cada paso en caché, y si
# el código cambia pero requirements.txt no, no se reinstalan las librerías.
COPY ${SERVICIO}/requirements.txt .

# --no-cache-dir: no guarda los instaladores de pip, la imagen queda más pequeña
# Instalación con reintentos y tiempo de espera extendido
RUN pip install --no-cache-dir --default-timeout=1000 --retries 10 -r requirements.txt

# Código compartido entre servicios (carpeta comun/) y luego el del servicio
COPY comun/ .
COPY ${SERVICIO}/ .

# Usuario sin privilegios; /modelos y /data se crean con su propietario
# (si alguien vulnera la aplicación, no obtiene permisos de root en el contenedor)
RUN useradd --create-home app && mkdir -p /modelos /data && chown app /modelos /data
USER app

# Documenta el puerto en el que escucha la aplicación dentro del contenedor
EXPOSE 8000

# Comando de arranque: uvicorn sirve la aplicación FastAPI "app" del archivo app.py.
# --host 0.0.0.0 acepta conexiones desde fuera del contenedor (no solo localhost).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]