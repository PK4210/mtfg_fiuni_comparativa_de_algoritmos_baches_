# Evaluación comparativa de Dijkstra, A\* y Bellman-Ford según la severidad de baches

Código y datos del Trabajo Final de Grado de **Pedro Kazlauskas Kondratiuk** y **Mohamed Ghaleb El Zein**, Facultad de Ingeniería — Universidad Nacional de Itapúa. Tutor: MSc. Nestor Tapia.

La memoria (MTFG) se redacta en el vault de Obsidian, `E:\Obsidian\PK4210\TFG\MTFG\`. Este repositorio contiene la canalización que produce los resultados del Capítulo 5. Implementa el protocolo del PTFG rev6 (Metodología de la Investigación).

---

## Qué hace

Construye un grafo dirigido de la red vial a partir de OpenStreetMap, le asigna los registros georreferenciados de baches, calcula la severidad de cada tramo, aplica una función de costo que la combina con la distancia y compara Dijkstra, A\* y Bellman-Ford sobre los mismos pares origen-destino.

| Concepto | Definición |
| --- | --- |
| Clase de un registro | Bache individual (aporta 1) o agrupación de baches próximos (aporta *b* = 12) |
| Severidad del tramo | `d(e) = baches(e) / ℓ(e)`, `s(e) = mín(1, d(e) / d95)` |
| Costo del tramo | `w(e) = ℓ(e) · [1 + α · s(e)]`, con α ∈ {0; 0,5; 1; 2; 5} |
| Heurística de A\* | Distancia euclidiana en coordenadas UTM; admisible porque `w(e) ≥ ℓ(e)` |
| Exposición de una ruta | Cantidad de baches de los tramos recorridos |

`ℓ(e)` se mide sobre la geometría del tramo en el plano UTM, no con la longitud esférica de OSMnx (ver más abajo).

### Clases por ciudad

- **Encarnación**: la clase la asignaron los autores del relevamiento mediante el color del ícono del KML (verde = individual, 322; azul = agrupación, 37). No se reagrupa.
- **Jersey City**: los registros son puntos sueltos y la clase se asigna con dos modelos, solo para esta ciudad.
  - **M1, proporción igualada**: se sortean exactamente el 10,3 % de los registros como agrupación (687 de 6.664), en 30 réplicas.
  - **M2, radio de 10 m**: los registros a ≤ 10 m entre sí, encadenados, forman un grupo, que se reduce a su centroide con clase agrupación. Salen 4.607 individuales y 798 agrupaciones.

---

## Instalación

Requiere Python 3.14 (el entorno de medición usó 3.14.5).

```bash
pip install -r requirements.txt
```

Las versiones están fijadas en `requirements.txt`.

## Uso

```bash
python src/ejecutar.py --area encarnacion
python src/ejecutar.py --area jersey_city            # modelos M1 y M2
python src/analisis.py --area encarnacion
python src/analisis.py --area jersey_city
python src/mapas.py --area encarnacion
python src/mapas.py --area jersey_city
python src/sensibilidad.py --area encarnacion        # complementario
python src/sensibilidad.py --area jersey_city
```

`--prueba` corre una muestra reducida (5 pares, 1 réplica) para comprobar que todo funciona. Sus salidas llevan el sufijo `_prueba`.

Tiempos en el equipo de medición: Encarnación tarda alrededor de 1,5 min; Jersey City, alrededor de 2 h, casi todo en las 30 réplicas de M1.

---

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `datos/crudos/` | Fuentes tal como se descargaron. No se editan nunca |
| `datos/derivados/` | Grafos y caché de OpenStreetMap (descarga del 03/09/2026) |
| `src/` | Módulos de la canalización |
| `resultados/tablas/` | Mediciones, resúmenes, pruebas estadísticas y verificación |
| `resultados/figuras/` | Gráficos, en PNG a 300 ppp y PDF |
| `resultados/mapas/` | Mapas de red, severidad, rutas y sentidos |
| `resultados/_diseño_anterior/` | Resultados del diseño previo (C2/C3). No se usan en la memoria |

| Módulo | Responsabilidad |
| --- | --- |
| `config.py` | Carga `config.yaml`. Ningún otro módulo define constantes |
| `preparacion.py` | Lectura, depuración y asignación de clase (observada, M1, M2) |
| `grafo.py` | Construcción, longitudes en UTM, asignación espacial, severidad y costo |
| `algoritmos.py` | Dijkstra, A\* y Bellman-Ford, instrumentados |
| `metricas.py` | Longitud, costo, exposición e informatividad de una ruta |
| `experimento.py` | Pares, cronometraje, verificación contra NetworkX y registro |
| `ejecutar.py` | Orquesta una corrida completa |
| `verificacion.py` | Integridad, admisibilidad, sentidos y coherencia de trazas |
| `analisis.py` | Resúmenes, Friedman, W de Kendall, Wilcoxon con Holm, aceleración de A\* y figuras |
| `mapas.py` | Mapas por ciudad y modelo |
| `sensibilidad.py` | Sensibilidad a *b* y al radio de M2 |
| `entorno.py` | Registra el equipo y las versiones en cada corrida |
| `trazas.py`, `animaciones.py` | Videos de la búsqueda (material extra, no forman parte de la memoria) |

---

## Protocolo de medición

- 200 pares por ciudad en la mayor componente fuertemente conexa, a ≥ 300 m en línea recta, sorteados con la semilla maestra. Son los mismos para los tres algoritmos, todos los α, ambos modelos y todas las réplicas.
- Cada consulta se repite 5 veces con `time.perf_counter_ns` y el recolector de basura suspendido; se descarta la primera y se guarda la mediana de las cuatro restantes, junto con los cuatro valores.
- Contadores:
  - nodos expandidos (Dijkstra y A\*);
  - relajaciones (toda evaluación de `d(u) + w(u, v)` frente a `d(v)`);
  - mejoras (las relajaciones que redujeron `d(v)`);
  - pasadas (Bellman-Ford).
- Bellman-Ford itera hasta que ninguna distancia cambia (formulación de Bellman, 1958) y luego verifica que no haya ciclos negativos.
- **Verificación en cada consulta**: los tres costos deben coincidir entre sí y con NetworkX (tolerancia relativa 10⁻⁹). `analisis.py` se niega a analizar una tabla con consultas no verificadas.

## Decisiones de implementación

- **Longitudes en el plano UTM.** OSMnx calcula `length` sobre una esfera, mientras que la heurística de A\* es una recta en UTM, que usa el elipsoide. En tramos este-oeste la longitud esférica quedaba por debajo de la recta, con 2 violaciones de admisibilidad en la prueba, de hasta 0,23 m. Por eso `ℓ(e)` se mide sobre la geometría proyectada; difiere de la de OSMnx en un 0,37 % como máximo. La de OSMnx se conserva en `length_osmnx`.
- **Duplicados.** Solo se descartan registros idénticos en todos sus campos. En Jersey City, 493 coordenadas se repiten en 2 o más registros, pero todos difieren en la fecha: son reparaciones distintas y se conservan las 6.664.
- **Sentidos de circulación.** Se toman de OpenStreetMap. Si hiciera falta corregir alguno, se agrega en `datos/crudos/sentidos_corregidos.csv` (`nombre_calle,sentido`, con `unico` o `doble`); hoy no tiene filas.

## Los datos

**Encarnación**: `datos/crudos/Capa Baches.kml`.
- Es el relevamiento ciudadano de J. Schmalko con estudiantes de Ingeniería de la UNI, de marzo de 2025.
- Cubre 2,89 km² del microcentro, delimitados por las avenidas Irrazábal, Caballero, Francia y Costanera República del Paraguay con calle Iturbe.
- Tiene 359 marcas, cada una con identificador, coordenadas, de 1 a 4 fotos y color. No incluye dimensiones ni severidad.

**Jersey City**: `datos/crudos/jersey_city_potholes.csv`.
- Es el conjunto «Pothole Map 2019» del Departamento de Obras Públicas, publicado en el portal oficial con licencia ODC-BY.
- Contiene 6.664 baches **reparados** entre el 18/01/2018 y el 30/10/2019.
- Cada registro trae dirección, latitud, longitud, distrito y fecha. No incluye severidad.

> La clase de los registros de Jersey City es **asignada** (M1 o M2), no observada. Los resultados sobre esa red informan sobre el desempeño de los algoritmos, no sobre el estado del pavimento de esa ciudad.

## Equipo de medición

PK-PC: Intel Core i5-14600K (14 núcleos físicos / 20 lógicos), 31,7 GB a 4800 MT/s, Windows 11 build 26200, Python 3.14.5. `entorno.py` lo registra en cada `estructura_<area>.json`. Las mediciones definitivas se toman sin otros procesos de carga significativa.
