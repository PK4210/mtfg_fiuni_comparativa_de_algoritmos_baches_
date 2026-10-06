"""Agregación de las mediciones, pruebas estadísticas y figuras del Capítulo 5.

Lee `resultados/tablas/mediciones_<area>.csv` y produce las tablas y figuras.
No mide nada: solo resume lo que `ejecutar.py` registró.

Unidad de análisis (PTFG rev6, protocolo, párrafos 5 y 6): la mediana de las
cuatro repeticiones válidas de cada consulta. Los 200 pares forman un diseño
pareado: el mismo par se resuelve con los tres algoritmos. En el modelo 1 de
Jersey City hay 30 réplicas del sorteo de clases sobre los mismos pares: las
pruebas usan, por par, el promedio de las 30 réplicas, y las tablas informan la
media y la desviación estándar de cada estadístico entre réplicas.

Pruebas, por ciudad, modelo y α:
  - Friedman sobre los tres algoritmos (bloques = pares), con la W de Kendall
    como tamaño del efecto;
  - si Friedman es significativa, Wilcoxon de rangos con signo para cada par
    de algoritmos, con los p-valores ajustados por el procedimiento de Holm;
  - factor de aceleración de A* respecto de Dijkstra.

Uso:
    python src/analisis.py --area encarnacion
"""
from __future__ import annotations

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
import numpy as np
import pandas as pd
from scipy import stats

from config import CFG, RES_FIGURAS, RES_TABLAS

ALGOS = ["dijkstra", "a_estrella", "bellman_ford"]
ETIQUETAS = {"dijkstra": "Dijkstra", "a_estrella": "A*", "bellman_ford": "Bellman-Ford"}
COLORES = {"dijkstra": "#2f5d7c", "a_estrella": "#9c4a21", "bellman_ford": "#4f8a5b"}
MARCAS = {"dijkstra": "o", "a_estrella": "s", "bellman_ford": "^"}
NOMBRE_MODELO = {"observado": "clase observada", "M1": "modelo 1 (proporción igualada)",
                 "M2": "modelo 2 (radio de 10 m)"}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.06,
})
CM = 1 / 2.54


def _num(x, _=None) -> str:
    """Número con coma decimal, como en el texto de la memoria."""
    return f"{x:g}".replace(".", ",")


def _formato_es(ax, x: bool = True, log: bool = False) -> None:
    if x:
        ax.xaxis.set_major_formatter(FuncFormatter(_num))
    ax.yaxis.set_major_formatter(FuncFormatter(_num))
    if log:
        ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1, 2, 5)))
        ax.yaxis.set_minor_formatter(NullFormatter())


# --- lectura ------------------------------------------------------------------
def leer(area: str) -> pd.DataFrame:
    ruta = RES_TABLAS / f"mediciones_{area}.csv"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta}. Ejecutá primero: python src/ejecutar.py --area {area}")
    df = pd.read_csv(ruta)
    if not df["verificado"].all():
        malos = df.loc[~df["verificado"], ["modelo", "replica", "alfa", "par"]].drop_duplicates()
        raise SystemExit(f"Hay {len(malos)} consultas que no superaron la verificación de costos: "
                         "la serie no es válida para comparar")
    return df


def desvio_relativo(df: pd.DataFrame) -> pd.DataFrame:
    """(L_α − L_0) / L_0 por par, algoritmo, modelo y réplica, en porcentaje."""
    base = df[df["alfa"] == 0.0][["modelo", "replica", "par", "algoritmo", "longitud_m"]]
    base = base.rename(columns={"longitud_m": "longitud_base"})
    df = df.merge(base, on=["modelo", "replica", "par", "algoritmo"], how="left")
    df["desvio_pct"] = 100 * (df["longitud_m"] - df["longitud_base"]) / df["longitud_base"]
    return df


# --- tablas ---------------------------------------------------------------------
def _estadisticos(g: pd.DataFrame) -> dict:
    """Estadísticos de un grupo (una réplica, un modelo, un α, un algoritmo)."""
    t = g["tiempo_ms"]
    return {
        "n_pares": len(g),
        "tiempo_ms_mediana": t.median(),
        "tiempo_ms_q1": t.quantile(.25),
        "tiempo_ms_q3": t.quantile(.75),
        "tiempo_ms_media": t.mean(),
        "expandidos_mediana": g["expandidos"].median(),
        "relajaciones_mediana": g["relajaciones"].median(),
        "pasadas_mediana": g["pasadas"].median(),
        "longitud_m_media": g["longitud_m"].mean(),
        "costo_media": g["costo"].mean(),
        "exposicion_media": g["exposicion"].mean(),
        "desvio_pct_media": g["desvio_pct"].mean(),
        "informatividad_media": g["informatividad"].mean(),
    }


def tabla_resumen(df: pd.DataFrame, area: str) -> pd.DataFrame:
    """Una fila por modelo, α y algoritmo. En M1: media y d. e. entre réplicas."""
    por_replica = (df.groupby(["modelo", "replica", "alfa", "algoritmo"])
                     .apply(lambda g: pd.Series(_estadisticos(g)), include_groups=False)
                     .reset_index())
    filas = []
    for (modelo, alfa, algo), g in por_replica.groupby(["modelo", "alfa", "algoritmo"]):
        fila = {"modelo": modelo, "alfa": alfa, "algoritmo": ETIQUETAS[algo],
                "replicas": len(g)}
        for col in g.columns:
            if col in ("modelo", "replica", "alfa", "algoritmo"):
                continue
            fila[col] = g[col].mean()
            if len(g) > 1 and col in ("tiempo_ms_mediana", "exposicion_media", "desvio_pct_media",
                                      "longitud_m_media"):
                fila[col + "_de_replicas"] = g[col].std(ddof=1)
        filas.append(fila)
    res = pd.DataFrame(filas)
    orden = {a: i for i, a in enumerate(ETIQUETAS.values())}
    res = res.sort_values(["modelo", "alfa", "algoritmo"], key=lambda s: s.map(orden) if s.name == "algoritmo" else s)
    res.round(5).to_csv(RES_TABLAS / f"resumen_{area}.csv", index=False)
    print(f"   tabla resumen -> resumen_{area}.csv")
    return res


def _holm(pvalores: list[float]) -> list[float]:
    """Ajuste de Holm (1979): p ordenados, multiplicados por (m − i), monótonos."""
    m = len(pvalores)
    orden = sorted(range(m), key=lambda i: pvalores[i])
    ajustados, acumulado = [0.0] * m, 0.0
    for rango, i in enumerate(orden):
        acumulado = max(acumulado, min(1.0, (m - rango) * pvalores[i]))
        ajustados[i] = acumulado
    return ajustados


def pruebas(df: pd.DataFrame, area: str) -> pd.DataFrame:
    """Friedman, W de Kendall, Wilcoxon con Holm y aceleración de A*, por modelo y α."""
    sig = CFG["experimento"]["significacion"]
    # por par: promedio entre réplicas (en M1) de la mediana de cada consulta
    por_par = (df.groupby(["modelo", "alfa", "par", "algoritmo"])["tiempo_ms"].mean()
                 .unstack("algoritmo").reset_index())
    filas = []
    for (modelo, alfa), g in por_par.groupby(["modelo", "alfa"]):
        g = g.dropna(subset=ALGOS)
        n, k = len(g), len(ALGOS)
        chi2, p_f = stats.friedmanchisquare(*[g[a].to_numpy() for a in ALGOS])
        fila = {"modelo": modelo, "alfa": alfa, "n_pares": n,
                "friedman_chi2": chi2, "friedman_p": p_f,
                "kendall_w": chi2 / (n * (k - 1)),
                "friedman_significativa": bool(p_f < sig)}
        comparaciones = [("dijkstra", "a_estrella"), ("dijkstra", "bellman_ford"),
                         ("a_estrella", "bellman_ford")]
        crudos = []
        for a, b in comparaciones:
            w, p = stats.wilcoxon(g[a], g[b])
            crudos.append(p)
            fila[f"wilcoxon_{a}_vs_{b}_W"] = w
            fila[f"wilcoxon_{a}_vs_{b}_p"] = p
        for (a, b), p_h in zip(comparaciones, _holm(crudos)):
            fila[f"wilcoxon_{a}_vs_{b}_p_holm"] = p_h
            fila[f"wilcoxon_{a}_vs_{b}_significativa"] = bool(fila["friedman_significativa"] and p_h < sig)
        cociente = g["dijkstra"] / g["a_estrella"]
        fila["aceleracion_astar_mediana_por_par"] = cociente.median()
        fila["aceleracion_astar_q1"] = cociente.quantile(.25)
        fila["aceleracion_astar_q3"] = cociente.quantile(.75)
        fila["aceleracion_astar_cociente_de_medianas"] = g["dijkstra"].median() / g["a_estrella"].median()
        fila["bellman_ford_sobre_dijkstra_mediana"] = (g["bellman_ford"] / g["dijkstra"]).median()
        filas.append(fila)
    res = pd.DataFrame(filas)
    res.to_csv(RES_TABLAS / f"pruebas_{area}.csv", index=False, float_format="%.6g")
    print(f"   pruebas estadísticas -> pruebas_{area}.csv")
    return res


def replicas_significativas(df: pd.DataFrame, area: str) -> pd.DataFrame | None:
    """En M1: en cuántas de las 30 réplicas Friedman resulta significativa."""
    m1 = df[df["modelo"] == "M1"]
    if m1.empty or m1["replica"].nunique() < 2:
        return None
    sig = CFG["experimento"]["significacion"]
    filas = []
    for (alfa, rep), g in m1.groupby(["alfa", "replica"]):
        t = g.pivot(index="par", columns="algoritmo", values="tiempo_ms").dropna()
        _, p = stats.friedmanchisquare(*[t[a] for a in ALGOS])
        filas.append({"alfa": alfa, "replica": rep, "p": p,
                      "aceleracion": (t["dijkstra"] / t["a_estrella"]).median()})
    r = pd.DataFrame(filas)
    res = r.groupby("alfa").agg(replicas=("p", "size"),
                                significativas=("p", lambda s: int((s < sig).sum())),
                                aceleracion_media=("aceleracion", "mean"),
                                aceleracion_de=("aceleracion", "std")).reset_index()
    res.to_csv(RES_TABLAS / f"replicas_m1_{area}.csv", index=False, float_format="%.6g")
    print(f"   réplicas del modelo 1 -> replicas_m1_{area}.csv")
    return res


# --- figuras ---------------------------------------------------------------------
def _guardar(fig, nombre: str) -> None:
    dpi = CFG["visualizacion"]["dpi_figuras"]
    for ext in ("png", "pdf"):
        fig.savefig(RES_FIGURAS / f"{nombre}.{ext}", dpi=dpi)
    plt.close(fig)
    print(f"   -> {nombre}.png")


def _paneles(modelos: list[str]):
    fig, ejes = plt.subplots(1, len(modelos), figsize=(15.5 * CM, 6.2 * CM), sharey=True,
                             squeeze=False)
    return fig, ejes[0]


def figura_tiempos(res: pd.DataFrame, area: str) -> None:
    """Mediana del tiempo de cómputo por algoritmo frente a α (escala logarítmica)."""
    modelos = list(res["modelo"].unique())
    fig, ejes = _paneles(modelos)
    for ax, modelo in zip(ejes, modelos):
        r = res[res["modelo"] == modelo]
        for algo in ALGOS:
            s = r[r["algoritmo"] == ETIQUETAS[algo]].sort_values("alfa")
            ax.errorbar(s["alfa"], s["tiempo_ms_mediana"],
                        yerr=[s["tiempo_ms_mediana"] - s["tiempo_ms_q1"],
                              s["tiempo_ms_q3"] - s["tiempo_ms_mediana"]],
                        color=COLORES[algo], marker=MARCAS[algo], ms=4, lw=1.2, capsize=2,
                        label=ETIQUETAS[algo])
        ax.set_yscale("log")
        _formato_es(ax, log=True)
        ax.set_xlabel("α")
        ax.set_title(NOMBRE_MODELO[modelo], fontsize=9)
        ax.grid(alpha=.3, which="both", lw=.4)
    ejes[0].set_ylabel("tiempo de cómputo [ms]")
    ejes[0].legend(frameon=False, fontsize=8)
    _guardar(fig, f"tiempos_{area}")


def figura_esfuerzo(res: pd.DataFrame, area: str) -> None:
    """Nodos expandidos por Dijkstra y A*, e informatividad de la heurística, frente a α."""
    modelos = list(res["modelo"].unique())
    fig, ejes = _paneles(modelos)
    for ax, modelo in zip(ejes, modelos):
        r = res[res["modelo"] == modelo]
        for algo in ("dijkstra", "a_estrella"):
            s = r[r["algoritmo"] == ETIQUETAS[algo]].sort_values("alfa")
            ax.plot(s["alfa"], s["expandidos_mediana"], color=COLORES[algo],
                    marker=MARCAS[algo], ms=4, lw=1.2, label=f"{ETIQUETAS[algo]}: nodos expandidos")
        ax2 = ax.twinx()
        s = r[r["algoritmo"] == "A*"].sort_values("alfa")
        ax2.plot(s["alfa"], s["informatividad_media"], color="#555", ls="--", lw=1, marker="x",
                 ms=4, label="A*: h(origen) / costo")
        ax2.set_ylim(0, 1.05)
        _formato_es(ax)
        _formato_es(ax2, x=False)
        if ax is ejes[-1]:
            ax2.set_ylabel("informatividad de la heurística")
        else:
            ax2.set_yticklabels([])
        ax.set_xlabel("α")
        ax.set_title(NOMBRE_MODELO[modelo], fontsize=9)
        ax.grid(alpha=.3, lw=.4)
    ejes[0].set_ylabel("nodos expandidos (mediana)")
    h1, l1 = ejes[0].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ejes[0].legend(h1 + h2, l1 + l2, frameon=False, fontsize=7.5, loc="upper left")
    _guardar(fig, f"esfuerzo_{area}")


def figura_compromiso(res: pd.DataFrame, area: str) -> None:
    """Exposición media frente a desvío medio de longitud, para cada α (rutas de Dijkstra)."""
    modelos = list(res["modelo"].unique())
    fig, ejes = _paneles(modelos)
    for ax, modelo in zip(ejes, modelos):
        s = res[(res["modelo"] == modelo) & (res["algoritmo"] == "Dijkstra")].sort_values("alfa")
        ax.plot(s["desvio_pct_media"], s["exposicion_media"], color="#2f5d7c", marker="o", ms=4, lw=1.2)
        rx = max(np.ptp(s["desvio_pct_media"]), 1e-9)
        ry = max(np.ptp(s["exposicion_media"]), 1e-9)
        previo = None
        for _, f in s.iterrows():
            x, y = f["desvio_pct_media"], f["exposicion_media"]
            # si el punto anterior está casi encima, la etiqueta va debajo para no superponerse
            cerca = previo is not None and abs(x - previo[0]) / rx < .05 and abs(y - previo[1]) / ry < .05
            ax.annotate(f"α = {_num(f['alfa'])}", (x, y), textcoords="offset points",
                        xytext=(5, -11) if cerca else (4, 3), fontsize=7)
            previo = (x, y)
        ax.margins(x=.2, y=.1)
        _formato_es(ax)
        ax.set_xlabel("desvío de longitud respecto de α = 0 [%]")
        ax.set_title(NOMBRE_MODELO[modelo], fontsize=9)
        ax.grid(alpha=.3, lw=.4)
    ejes[0].set_ylabel("exposición media [baches por ruta]")
    _guardar(fig, f"compromiso_{area}")


def figura_replicas(df: pd.DataFrame, area: str) -> None:
    """Modelo 1: distribución entre réplicas de la exposición media y de la aceleración de A*."""
    m1 = df[df["modelo"] == "M1"]
    if m1.empty or m1["replica"].nunique() < 2:
        return
    alfas = sorted(m1["alfa"].unique())
    expo = [m1[(m1["alfa"] == a) & (m1["algoritmo"] == "dijkstra")].groupby("replica")["exposicion"].mean()
            for a in alfas]
    acel = []
    for a in alfas:
        t = m1[m1["alfa"] == a].pivot_table(index=["replica", "par"], columns="algoritmo", values="tiempo_ms")
        acel.append((t["dijkstra"] / t["a_estrella"]).groupby("replica").median())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5 * CM, 6.2 * CM), layout="constrained")
    mediana = {"color": "#9c4a21", "lw": 1.2}
    ax1.boxplot(expo, tick_labels=[_num(a) for a in alfas], widths=.5, medianprops=mediana)
    ax1.set_xlabel("α")
    ax1.set_ylabel("exposición media [baches por ruta]")
    ax2.boxplot(acel, tick_labels=[_num(a) for a in alfas], widths=.5, medianprops=mediana)
    ax2.set_xlabel("α")
    ax2.set_ylabel("aceleración de A* (mediana por réplica)")
    for ax in (ax1, ax2):
        ax.grid(alpha=.3, lw=.4)
        _formato_es(ax, x=False)
    _guardar(fig, f"replicas_m1_{area}")


def verificacion(df: pd.DataFrame, area: str) -> None:
    """Resumen de la verificación de costos: consultas verificadas por modelo y α."""
    v = (df.groupby(["modelo", "alfa"])
           .agg(consultas=("verificado", "size"), verificadas=("verificado", "sum")).reset_index())
    v.to_csv(RES_TABLAS / f"verificacion_{area}.csv", index=False)
    print(f"   verificación: {int(v['verificadas'].sum())} de {int(v['consultas'].sum())} "
          "consultas con costo idéntico entre los tres algoritmos y NetworkX")


def main() -> None:
    p = argparse.ArgumentParser(description="Análisis del Capítulo 5")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    p.add_argument("--prueba", action="store_true", help="analiza la corrida de prueba")
    args = p.parse_args()

    area = args.area + ("_prueba" if args.prueba else "")
    print(f"== análisis: {area}")
    df = desvio_relativo(leer(area))
    verificacion(df, area)
    res = tabla_resumen(df, area)
    pr = pruebas(df, area)
    replicas_significativas(df, area)
    figura_tiempos(res, area)
    figura_esfuerzo(res, area)
    figura_compromiso(res, area)
    figura_replicas(df, area)
    resumen = pr[["modelo", "alfa", "friedman_p", "kendall_w",
                  "aceleracion_astar_mediana_por_par"]].round(4)
    print(resumen.to_string(index=False))


if __name__ == "__main__":
    main()
