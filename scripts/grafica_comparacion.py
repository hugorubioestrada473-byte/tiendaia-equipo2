import matplotlib.pyplot as plt

nan = float("nan")  # los valores nan no se dibujan: sirven de marcador

workers = [1, 2, 4, 8]

# Promedio de las 3 repeticiones (sol/s) por cada cantidad de workers
local = [4.3, 8.4, 13.9, 14.3]      # laptop, 12 núcleos
codespace = [3.7, nan, nan, nan]    # REEMPLAZA con tus promedios del codespace

plt.figure(figsize=(7, 4.5))
plt.plot(workers, local, marker="o", label="Local (12 núcleos)")
plt.plot(workers, codespace, marker="s", label="Codespace (2 núcleos, 7.8 GiB RAM)")

plt.xticks(workers)
plt.xlabel("Número de workers")
plt.ylabel("Rendimiento (solicitudes/s)")
plt.title("Rendimiento vs. número de workers")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig("figura_comparacion.png", dpi=200)
print("Guardado: figura_comparacion.png")