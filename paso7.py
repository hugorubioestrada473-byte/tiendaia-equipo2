import pandas as pd
import matplotlib.pyplot as plt

# --- 1. CARGAR DATOS Y CREAR TABLA COMPARATIVA CSV ---
df = pd.read_csv("resultados_almacenamiento.csv", encoding="latin1")

# Formatear valor como "media +/- desv"
df["valor"] = df["media"].astype(str) + " +/- " + df["desv"].astype(str)

# Crear tabla pivote: filas=prueba, columnas=destino
tabla = df.pivot_table(index="prueba", columns="destino", values="valor", aggfunc="last")

print("=== TABLA COMPARATIVA ===")
print(tabla.to_string())

# Guardar la tabla comparativa a CSV
tabla.to_csv("tabla_comparativa.csv")


# --- 2. GRÁFICA 1: SUBIDA (MB/s) ---
sub = df[df["prueba"].str.startswith("subida")].copy()
sub["mb"] = sub["prueba"].str.split().str[1].astype(int)

plt.figure(figsize=(8, 5))
for destino, d in sub.groupby("destino"):
    d_grouped = d.groupby("mb")[["media", "desv"]].last()
    plt.errorbar(d_grouped.index, d_grouped["media"], yerr=d_grouped["desv"], marker="o", capsize=3, label=destino)

plt.xlabel("Tamaño del archivo (MB)")
plt.ylabel("Subida (MB/s)")
plt.title("Rendimiento de Subida por Destino")
plt.legend()
plt.grid(True)
plt.savefig("grafica_subida.png", dpi=150)
plt.close()


# --- 3. GRÁFICA 2: BAJADA (MB/s) ---
baj = df[df["prueba"].str.startswith("bajada")].copy()
baj["mb"] = baj["prueba"].str.split().str[1].astype(int)

plt.figure(figsize=(8, 5))
for destino, d in baj.groupby("destino"):
    d_grouped = d.groupby("mb")[["media", "desv"]].last()
    plt.errorbar(d_grouped.index, d_grouped["media"], yerr=d_grouped["desv"], marker="s", capsize=3, label=destino)

plt.xlabel("Tamaño del archivo (MB)")
plt.ylabel("Bajada (MB/s)")
plt.title("Rendimiento de Bajada por Destino")
plt.legend()
plt.grid(True)
plt.savefig("grafica_bajada.png", dpi=150)
plt.close()


# --- 4. GRÁFICA 3: BARRAS - ARCHIVOS/S POR DESTINO ---
arch = df[df["prueba"].isin(["rendimiento pequenos", "200 archivos de 10 KB"])].copy()

if not arch.empty:
    plt.figure(figsize=(8, 5))
    arch_pivot = arch.pivot_table(index="prueba", columns="destino", values="media", aggfunc="last")
    arch_pivot.plot(kind="bar", figsize=(8, 5))
    plt.xlabel("Prueba")
    plt.ylabel("Archivos / s (o Tiempo en ms)")
    plt.title("Rendimiento de Archivos Pequeños por Destino")
    plt.xticks(rotation=0)
    plt.legend()
    plt.grid(axis='y')
    plt.tight_layout()
    plt.savefig("grafica_archivos_segundo.png", dpi=150)
    plt.close()

print("\n¡Proceso completado con éxito!")