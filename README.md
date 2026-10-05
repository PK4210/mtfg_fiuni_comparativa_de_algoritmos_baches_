# Comparación de Dijkstra, A\* y Bellman-Ford sobre grafos viales ponderados por el estado del pavimento

Código y datos del Trabajo Final de Grado de **Pedro Kazlauskas Kondratiuk** y **Mohamed Ghaleb El Zein**, Facultad de Ingeniería — Universidad Nacional de Itapúa.

La memoria se redacta aparte, en `E:\Obsidian\PK4210\TFG\MTFG\`. Este repositorio contiene la canalización que produce los resultados del Capítulo 5.

---

## Qué hace

Construye un grafo dirigido ponderado de la red vial a partir de OpenStreetMap, le asigna la información georreferenciada de baches, aplica una función de costo que penaliza los tramos deteriorados y compara el desempeño de tres algoritmos de caminos mínimos sobre él.

La función de costo es `w(e) = ℓ(e) · [1 + α · s(e)]`, donde `ℓ(e)` es la longitud del tramo, `s(e)` un índice de deterioro acotado a [0, 1] y `α` un parámetro que regula cuánto se penaliza el deterioro. Con `α = 0` el costo es distancia pura, que sirve de línea de base.

---

## Instalación

Requiere Python 3.10 o superior.

```bash
pip install -r requirements.txt
```

`osmnx` arrastra `geopandas`, `shapely` y `rtree`. En Windows la instalación con `pip` funciona sin pasos adicionales.

---

## Uso

Desde la raíz del proyecto:

```bash
python src/ejecutar.py --area encarnacion
python src/analisis.py --area encarnacion
```

Para la red de contraste, con las dos configuraciones de clases:

```bash
python src/ejecutar.py --area jersey_city --config C2 C3
python src/analisis.py --area jersey_city
```

Para comprobar que todo corre sin esperar la serie completa:

```bash
python src/ejecutar.py --area encarnacion --prueba
```

La primera ejecución descarga la red vial de OpenStreetMap y la guarda en `datos/derivados/`; las siguientes la reutilizan.

---

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `datos/crudos/` | Fuentes tal como se descargaron, sin modificar. No se editan nunca |
| `datos/derivados/` | Grafos construidos y artefactos intermedios. Se regeneran solos |
| `src/` | Los módulos de la canalización |
| `resultados/tablas/` | Mediciones en bruto, resumen comparativo y verificación |
| `resultados/figuras/` | Gráficos comparativos, en PNG a 300 ppp y PDF vectorial |
| `resultados/mapas/` | Mapas de las rutas calculadas |
| `notebooks/` | Cuadernos de exploración |
| `docs/` | Notas de análisis |

### Los módulos

Se corresponden uno a uno con los descritos en la sección 4.2 de la memoria.

| Módulo | Responsabilidad |
| --- | --- |
| `config.py` | Carga `config.yaml`. Ningún otro módulo define constantes |
| `preparacion.py` | Lee las fuentes, las depura y resuelve la clase de cada registro |
| `grafo.py` | Construye, proyecta, asigna la severidad y pondera |
| `algoritmos.py` | Dijkstra, A\* y Bellman-Ford, instrumentados |
| `metricas.py` | Longitud, tiempo, exposición y costo sobre una ruta |
| `experimento.py` | Genera los pares, ejecuta las repeticiones y registra |
| `verificacion.py` | Las comprobaciones de la sección 3.2.6 |
| `entorno.py` | Registra el equipo, el disco del proyecto y las versiones en cada corrida |
| `ejecutar.py` | Orquesta la canalización completa |
| `analisis.py` | Agrega las mediciones y produce tablas y figuras |
| `trazas.py` | Los mismos algoritmos, registrando el orden de expansión |
| `mapas.py` | Mapas de red, de deterioro y de auditoría de sentidos |
| `animaciones.py` | Videos de la búsqueda paso a paso |

---

## Mapas y videos

```bash
python src/mapas.py --area encarnacion
python src/animaciones.py --area encarnacion
```

Todo va a `resultados/mapas/`.

**Tres mapas por ciudad**, en PNG a 300 ppp y PDF:

| Archivo | Qué muestra |
| --- | --- |
| `red_<ciudad>` | La red vial con sus intersecciones y los baches superpuestos, con las agrupaciones dibujadas más grandes |
| `severidad_<ciudad>` | Cada tramo coloreado por su índice de deterioro `s(e)`, que es lo que penaliza la función de costo |
| `sentidos_<ciudad>` | Auditoría del sentido de circulación, con flechas y nombres de calle |

**Cinco videos por ciudad**, uno por valor de α, en MP4, más el cuadro final de cada uno como figura estática (`expansion_<ciudad>_alfa<valor>.png`, 300 ppp). Panel triple con los tres algoritmos sobre el mismo par origen-destino.

La expansión no se dibuja como puntos en las intersecciones sino **sobre la geometría real de cada calle**: se ve la búsqueda avanzar por la red. Cuatro capas por panel:

| Capa | Qué es |
| --- | --- |
| Árbol de exploración | La unión de las aristas `(pred[v], v)` de los nodos ya cerrados. Las recién exploradas van brillantes y las viejas se atenúan: se ve el frente de onda avanzar |
| Camino al nodo que se expande | Desde el origen hasta el nodo que el algoritmo acaba de cerrar, en trazo oscuro |
| Mejor camino tentativo al destino | En violeta, desde que el destino recibe una distancia tentativa hasta que se vuelve la ruta definitiva |
| Frontera y ruta final | Anillos en los nodos en cola; al terminar, la ruta y su costo |

Dijkstra y A\* comparten unidad —nodos expandidos— y avanzan sobre la misma línea de tiempo, de modo que A\* termina antes y su panel queda congelado mientras Dijkstra sigue explorando. Esa asimetría es el resultado que interesa mostrar.

**El camino resaltado de Dijkstra salta de un lado a otro del frente.** No es un defecto del video: Dijkstra cierra nodos por orden de distancia y no apunta a ningún lado, así que dos expansiones consecutivas caen en extremos opuestos del anillo. En A\* el mismo trazo avanza dirigido hacia el destino. Ese contraste es la hipótesis de §2.5 hecha imagen.

Bellman-Ford no expande nodos sino que relaja todas las aristas en cada pasada, así que su unidad no es comparable: avanza por pasadas y el rótulo lo aclara. Su árbol además **se recablea** entre pasadas, de modo que se dibuja el vigente en cada una y no la unión histórica: las ramas que todavía cambian quedan brillantes.

El par origen-destino es el mismo para los cinco valores de α de una ciudad, elegido de forma determinista del cuartil superior de distancia, para que las diferencias entre videos sean atribuibles solo a la función de costo.

---

## Sentidos de circulación

**Los recorridos respetan las restricciones de dirección.** No es algo que haya que activar: el grafo es dirigido, OSMnx traduce la etiqueta `oneway` de OpenStreetMap en aristas dirigidas, y los tres algoritmos recorren solo aristas salientes. `verificacion.py` lo comprueba en cada corrida recorriendo las rutas tramo por tramo; si alguna circulara en contramano, aparecería en `estructura_<area>.json` bajo `sentidos_respetados`. `expansion_dibujable` extiende la comprobación a **todo lo que el video muestra**: cada arista del árbol de exploración y cada camino resaltado tiene que existir como arista dirigida y arrancar en el origen.

Cosa distinta es si el dato de OSM refleja la realidad. En el microcentro de Encarnación, OSM declara 342 tramos de sentido único y 6 de doble. El mapa de auditoría muestra que **las calles paralelas consecutivas alternan de sentido**, que es la firma de una grilla de mano única real, y que las avenidas divididas —Costanera, Irrazábal— aparecen como dos calzadas paralelas, que es el modelado correcto. Aun así conviene recorrer el mapa y comprobarlo contra el terreno.

Si algo está mal, se corrige en `datos/crudos/sentidos_corregidos.csv` sin tocar el código ni editar OpenStreetMap:

```
nombre_calle,sentido
Curupayty,doble
Villarrica,unico
```

`grafo.py` lo aplica al construir el grafo: pasar una calle a doble sentido agrega la arista recíproca, pasarla a sentido único la elimina. Cuántas aristas se modificaron queda registrado en `estructura_<area>.json`. Mientras el archivo no tenga filas de datos, el grafo queda tal como lo entrega OSM.

---

## Configuración

**Todo se cambia en `config.yaml`.** El código no contiene constantes del experimento: si hay que ajustar el radio de tolerancia, los valores de α o la cantidad de baches que representa una agrupación, se cambia ahí y en ningún otro lado.

Los parámetros que más conviene revisar antes de una corrida definitiva:

| Parámetro | Valor actual | Qué controla |
| --- | --- | --- |
| `semilla_maestra` | 20260903 | De ella se derivan todas las demás. Sin ella el experimento no es reproducible |
| `experimento.pares_od` | 200 | Pares origen-destino por condición |
| `experimento.repeticiones` | 5 | Cronometrajes por par; se descarta el primero |
| `experimento.distancia_minima_m` | 300 | Evita pares triviales dentro de la misma cuadra |
| `experimento.replicas_asignacion` | 30 | Solo en la red de contraste, donde la clase se sortea |
| `experimento.limite_pares_bellman_ford` | 30 | Bellman-Ford es O(n·m): sin tope, la corrida se vuelve inviable |
| `costo.alfas` | 0 · 0,5 · 1 · 2 · 5 | Configuraciones de la función de costo |
| `asignacion.radio_tolerancia_m` | 20 | Si es chico se pierden baches; si es grande se asignan a la calle vecina |
| `clases.baches_representados.agrupacion` | 12 | Cuántos baches representa una marca azul del relevamiento |

---

## Los datos

**Encarnación** — `datos/crudos/Capa Baches.kml`. Relevamiento ciudadano de Juan Schmalko con estudiantes de Ingeniería de la UNI, difundido el 16 de marzo de 2025. Cubre 2,89 km² del microcentro delimitados por las avenidas Irrazábal, Caballero, Francia y Costanera República del Paraguay con la calle Iturbe.

Contiene **359 marcas**, cada una con coordenadas y fotografía. La clase no es un campo de texto: está codificada en el color del icono, y por eso `preparacion.py` resuelve la referencia de estilo del KML.

- Verde `#0F9D58` → bache individual: **322 marcas, 89,69 %**
- Azul `#0288D1` → agrupación de varios baches: **37 marcas, 10,31 %**

Dos condiciones acotan la lectura de estas cifras. Las marcas no guardan correspondencia unívoca con los baches, porque en los sectores más deteriorados el relevamiento agrupó varios bajo una sola marca: el autor estima en más de 750 los puntos que habría dado un registro individual. Y solo se registraron baches de magnitud considerable, no imperfecciones menores.

**Jersey City** — `datos/crudos/jersey_city_potholes.csv`. Conjunto «Pothole Map 2019» del Departamento de Obras Públicas, licencia ODC-BY. **6.664 registros** entre el 18 de enero de 2018 y el 30 de octubre de 2019.

Esta fuente **no publica ningún atributo de gravedad**, y sus registros corresponden a baches **ya reparados**. Por indicación de la tutoría se le transfiere la distribución de clases observada en Encarnación, con proporciones exactas y permutación aleatoria.

> **Importante.** La clase asignada a cada registro de Jersey City es un atributo **sintético**: no describe el estado real de ese bache. Los resultados sobre esa red informan sobre el desempeño de los algoritmos y en ningún caso sobre la condición del pavimento de esa ciudad.

---

## Verificación

`verificacion.py` corre en cada ejecución y deja su salida en `resultados/tablas/estructura_<area>.json`. Comprueba cuatro cosas:

1. **Optimalidad cruzada.** Los tres algoritmos deben devolver rutas del mismo costo. Cualquier diferencia es un defecto de implementación.
2. **Contraste contra NetworkX.** El costo propio debe coincidir con el de la implementación de referencia.
3. **Admisibilidad de la heurística.** `h(n)` nunca debe superar el costo real mínimo hasta el destino. Es lo que garantiza que A\* siga encontrando la ruta óptima bajo la función de costo penalizada.
4. **Integridad del grafo.** Sin aristas de longitud nula, sin pesos negativos, sin severidades fuera de rango, sin nodos sin coordenadas.
5. **Sentidos respetados.** Cada tramo de cada ruta debe corresponder a una arista dirigida saliente. Ninguna ruta puede ir en contramano.
6. **Trazas coherentes.** El número de nodos que registra `trazas.py` debe coincidir con el que cuenta `algoritmos.py`: la instrumentación para animar no puede alterar el comportamiento.

En la última corrida las cuatro pasaron sin discrepancias en ambas redes.

---

## Estado actual

Lo verificado hasta ahora, con la configuración por defecto:

| | Encarnación | Jersey City |
| --- | --- | --- |
| Nodos | 202 | 3.502 |
| Aristas | 348 | 8.149 |
| Longitud de la red | 42,8 km | 1.028,9 km |
| Registros retenidos | 359 | 5.997 |
| Aristas con deterioro | 187 (53,7 %) | 2.073 (25,4 %) |

El contraste de escala es real: la red de Jersey City tiene diecisiete veces más nodos.

### Sobre las mediciones de tiempo

Las mediciones se obtuvieron en el equipo declarado en la Tabla 4.5 de la memoria, y cada corrida lo registra automáticamente en `estructura_<area>.json`:

| | |
| --- | --- |
| Equipo | PK-PC |
| Procesador | Intel Core i5-14600K, 14 núcleos físicos / 20 lógicos |
| Memoria | 31,7 GB a 4800 MT/s |
| Almacenamiento | Kingston SUV400S37240G, SATA, 240 GB (unidad `E:`, donde vive el proyecto) |
| Sistema operativo | Windows 11 build 26200 |
| Python | 3.14.5 |

`entorno.py` captura esta ficha en cada ejecución, de modo que ninguna tabla de resultados queda sin el contexto donde se produjo. Si alguna vez se corre en otra máquina, el JSON lo delata solo.

Para la **serie definitiva** conviene repetir la corrida con los demás programas cerrados: los tiempos que hay ahora se tomaron durante el desarrollo, con una sesión interactiva abierta, y aunque el equipo es el correcto las condiciones no fueron las controladas que la memoria declara en la sección 4.7.

Conviene además **no medir en cuadernos alojados en línea**: el procesador asignado varía entre sesiones y se comparte con otras cargas, de modo que los tiempos no serían comparables ni reproducibles. Esos entornos sirven para explorar los datos, no para cronometrar.

### Un detalle del análisis

Bellman-Ford se ejecuta sobre menos pares que los otros dos, porque su costo es O(n·m). Por eso `analisis.py` restringe todas las métricas a los pares que los tres resolvieron: comparar medias calculadas sobre muestras distintas produciría diferencias que no son atribuibles a los algoritmos.

---

## Qué falta

- Repetir la serie definitiva con los demás programas cerrados.
- Ampliar el recuadro de Jersey City si se quiere abarcar los 667 registros que hoy quedan fuera por duplicación de coordenadas.
- Recorrer el mapa de sentidos y corregir lo que no coincida con la realidad.
- Volcar las tablas y figuras al Capítulo 5 de la memoria.
