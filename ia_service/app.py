"""Microservicio de IA de TiendaIA: predicción de demanda (Laboratorio 2).
Entrena un modelo RandomForest (scikit-learn) que estima cuántas unidades se
venderán de un producto según el mes y el precio. Los datos de entrenamiento se
piden por HTTP al microservicio Ventas (no lee su base de datos). El modelo
entrenado se guarda en disco (volumen de Docker) para usarlo en las predicciones.
"""
import os
from pathlib import Path
import joblib
import pandas as pd
import requests  # cliente HTTP para pedir las ventas al microservicio Ventas
from fastapi import FastAPI, HTTPException, Query
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from cola import router as cola_router 

# ---------------------------------------------------------------- Configuración
VENTAS_URL = os.getenv("VENTAS_URL", "http://ventas:8000")

# Ruta del archivo del modelo. En Docker, /modelos es un volumen: el modelo
# sobrevive aunque el contenedor se borre y se vuelva a crear.
MODELO = Path(os.getenv("MODELO_PATH", "/modelos/modelo.joblib"))
COLUMNAS = ["producto_id", "mes", "precio"]  # variables de entrada (features)

app = FastAPI(title="TiendaIA - Servicio de IA")
app.include_router(cola_router) 

def preparar(ventas: list[dict]) -> pd.DataFrame:
    """Convierte la lista de ventas (JSON) en un DataFrame y agrega la columna mes.
    El mes (1 a 12) se extrae de la fecha porque la demanda suele variar por
    temporada; el modelo no puede usar una fecha de texto directamente.
    """
    df = pd.DataFrame(ventas)
    df["mes"] = pd.to_datetime(df["fecha"]).dt.month
    return df


# ---------------------------------------------------------------- Endpoints
@app.get("/health")
def salud():
    """Verificación de salud (200); indica además si ya existe un modelo entrenado."""
    return {"servicio": "ia", "status": "ok", "modelo_entrenado": MODELO.exists()}


@app.post("/ia/train")
def entrenar():
    """Entrena el modelo con todas las ventas y lo guarda en disco.
    Devuelve cuántas ventas se usaron y dos métricas sobre datos de prueba:
    MAE (error absoluto medio, en unidades) y R2 (1 = predicción perfecta).
    Responde 200, o 400 si hay menos de 30 ventas (muy pocos datos para aprender).
    """
    # Pide los datos al servicio de Ventas: no lee su base de datos.
    # timeout=30: entrenar no es urgente, pero tampoco se espera para siempre.
    ventas = requests.get(f"{VENTAS_URL}/ventas", timeout=30).json()
    if len(ventas) < 30:
        raise HTTPException(
            400, f"Se requieren al menos 30 ventas (hay {len(ventas)})"
        )

    df = preparar(ventas)
    X, y = (
        df[COLUMNAS],
        df["cantidad"],
    )  # X = entradas, y = lo que se quiere predecir

    # Se separa 20 % de los datos para evaluar con ventas que el modelo no vio.
    # random_state fija el azar: el resultado es repetible.
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Pipeline: primero transforma las columnas y luego aplica el modelo.
    # OneHotEncoder convierte producto_id en columnas 0/1, porque el id es una
    # categoría (el producto 4 no es "el doble" del producto 2).
    # remainder="passthrough" deja mes y precio tal como vienen.
    modelo = make_pipeline(
        ColumnTransformer(
            [("prod", OneHotEncoder(handle_unknown="ignore"), ["producto_id"])],
            remainder="passthrough",
        ),
        # Bosque aleatorio: promedia 200 árboles de decisión para reducir errores
        RandomForestRegressor(n_estimators=200, random_state=42),
    )

    modelo.fit(X_tr, y_tr)  # aprendizaje con el 80 % de los datos
    pred = modelo.predict(X_te)  # predicción sobre el 20 % reservado

    MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODELO)  # serializa el modelo entrenado a un archivo

    return {
        "mensaje": "Modelo entrenado",
        "ventas": len(df),
        "mae": round(mean_absolute_error(y_te, pred), 2),
        "r2": round(r2_score(y_te, pred), 3),
    }


@app.get("/ia/predict")
def predecir(
    producto_id: int,
    mes: int = Query(ge=1, le=12),
    precio: float = Query(gt=0),
):
    """Estima la cantidad que se venderá de un producto en un mes y a un precio.
    Los datos llegan como parámetros de consulta (?producto_id=1&mes=5&precio=10).
    Query(ge=1, le=12) obliga a un mes válido y Query(gt=0) a un precio positivo;
    si no se cumplen, FastAPI responde 422. Responde 200 con la estimación, o
    409 si todavía no se ha entrenado el modelo (el estado actual no lo permite).
    """
    if not MODELO.exists():
        raise HTTPException(
            409, "Modelo no entrenado: ejecute POST /api/ia/train"
        )

    modelo = joblib.load(MODELO)  # carga el modelo guardado por /ia/train

    # Un DataFrame de una sola fila con las mismas columnas usadas al entrenar
    x = pd.DataFrame([[producto_id, mes, precio]], columns=COLUMNAS)
    return {
        "producto_id": producto_id,
        "mes": mes,
        "precio": precio,
        "cantidad_estimada": round(float(modelo.predict(x)[0]), 1),
    }