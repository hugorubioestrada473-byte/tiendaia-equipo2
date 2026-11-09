import matplotlib.pyplot as plt

workers  = [1, 2, 4, 8]
reps     = [[4.3, 4.3, 4.3], [8.3, 8.4, 8.4], [13.8, 13.9, 13.9], [13.7, 15.5, 13.7]]
promedio = [sum(r) / len(r) for r in reps]
teorico  = [5, 10, 20, 40]

plt.figure(figsize=(7, 4.5))
plt.plot(workers, promedio, "o-", label="Medido (promedio de 3 rep.)")
plt.plot(workers, teorico, "s--", label="Máximo teórico (5 sol/s por worker)")
for w, p in zip(workers, promedio):
    plt.annotate(f"{p:.1f}", (w, p), textcoords="offset points", xytext=(0, -15), ha="center")
plt.xscale("log", base=2)
plt.xticks(workers, workers)
plt.xlabel("Número de workers")
plt.ylabel("Rendimiento (solicitudes/s)")
plt.title("Rendimiento vs. número de workers")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig("rendimiento.png", dpi=150)
plt.show()