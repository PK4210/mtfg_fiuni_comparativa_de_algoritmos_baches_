"""Auditoría del sentido de circulación: página interactiva y tabla por tramo.

Para cada arista del grafo de un área produce el nombre de la calle, las calles
transversales en sus extremos, si es de mano única o doble y hacia dónde
circula, y enlaces a Google Maps y a Street View en el punto medio del tramo,
para contrastar a mano lo que declara OpenStreetMap. Las diferencias se
corrigen en `datos/crudos/sentidos_corregidos.csv`; la página permite marcar
las calles con error y descargar ese archivo.

Salidas, en `resultados/mapas/`:
  sentidos_<ciudad>.html   mapa interactivo (Leaflet) con flechas y tabla
  sentidos_<ciudad>.csv    la misma tabla, un tramo por fila

Uso:
    python src/auditoria_sentidos.py --area encarnacion
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math

from pyproj import Transformer

from config import CFG, RES_MAPAS, area as cfg_area
import grafo as gr

PUNTOS = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]


def rumbo(x1, y1, x2, y2) -> float:
    """Rumbo en grados desde el norte, en sentido horario (coordenadas proyectadas)."""
    return (math.degrees(math.atan2(x2 - x1, y2 - y1)) + 360) % 360


def cardinal(grados: float) -> str:
    return PUNTOS[int((grados + 22.5) // 45) % 8]


def transversales(G, nodo, propio: str) -> str:
    nombres = set()
    for u, v, d in list(G.in_edges(nodo, data=True)) + list(G.out_edges(nodo, data=True)):
        n = gr._nombre_calle(d)
        if n and n != propio:
            nombres.add(n)
    return " / ".join(sorted(nombres)) or "(sin nombre o extremo de la red)"


def tramos(G, epsg: int) -> list[dict]:
    a_grados = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    pares = {(u, v) for u, v, _ in G.edges(keys=True)}
    vistos, filas = set(), []
    for u, v, k, d in G.edges(keys=True, data=True):
        doble = (v, u) in pares
        if doble and (v, u, k) in vistos:
            continue                      # el tramo de doble mano se lista una vez
        vistos.add((u, v, k))
        geom = d.get("geometry")
        if geom is not None:
            coords = list(geom.coords)
            medio = geom.interpolate(.5, normalized=True)
            a, b = geom.interpolate(.45, normalized=True), geom.interpolate(.55, normalized=True)
        else:
            coords = [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
            mx, my = (coords[0][0] + coords[1][0]) / 2, (coords[0][1] + coords[1][1]) / 2
            medio = type("P", (), {"x": mx, "y": my})()
            a = type("P", (), {"x": coords[0][0], "y": coords[0][1]})()
            b = type("P", (), {"x": coords[1][0], "y": coords[1][1]})()
        grados = rumbo(a.x, a.y, b.x, b.y)
        lon, lat = a_grados.transform(medio.x, medio.y)
        nombre = gr._nombre_calle(d) or "(sin nombre)"
        filas.append({
            "id": len(filas) + 1,
            "calle": nombre,
            "desde": transversales(G, u, nombre),
            "hasta": transversales(G, v, nombre),
            "sentido": "doble" if doble else "único",
            "hacia": "ambos sentidos" if doble else cardinal(grados),
            "rumbo": round(grados),
            "tipo_via": d.get("highway") if isinstance(d.get("highway"), str) else ", ".join(d.get("highway", [])),
            "longitud_m": round(d["length"], 1),
            "lat": round(lat, 6), "lon": round(lon, 6),
            "linea": [[round(y, 6), round(x, 6)] for x, y in
                      (a_grados.transform(px, py) for px, py in coords)],
            "google_maps": f"https://www.google.com/maps/@{lat:.6f},{lon:.6f},19z",
            "street_view": (f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}"
                            f"&heading={round(grados)}"),
        })
    filas.sort(key=lambda f: (f["calle"], f["desde"]))
    for i, f in enumerate(filas, 1):
        f["id"] = i
    return filas


PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentidos de circulación — __TITULO__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-polylinedecorator@1.6.0/dist/leaflet.polylineDecorator.js"></script>
<style>
:root{--fondo:#fafaf8;--texto:#1d2329;--suave:#5f6b75;--borde:#d9dde1;--unico:#2f5d7c;--doble:#4f8a5b;--malo:#b3261e}
@media (prefers-color-scheme:dark){:root{--fondo:#15191d;--texto:#e6e9ec;--suave:#9aa5ae;--borde:#2c343b}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);font:15px/1.45 "Liberation Serif",Georgia,serif}
header{padding:14px 16px 6px}h1{font-size:20px;margin:0 0 4px}p{margin:4px 0;color:var(--suave)}
#mapa{height:62vh;min-height:360px;border-top:1px solid var(--borde);border-bottom:1px solid var(--borde)}
.barra{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 16px}
input[type=search]{flex:1;min-width:200px;padding:7px 9px;border:1px solid var(--borde);border-radius:6px;background:transparent;color:var(--texto)}
button{padding:7px 12px;border:1px solid var(--borde);border-radius:6px;background:transparent;color:var(--texto);cursor:pointer}
.tabla{overflow-x:auto;padding:0 16px 24px}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid var(--borde);padding:6px 6px;text-align:left;vertical-align:top}th{position:sticky;top:0;background:var(--fondo)}
tr.marcado td{background:rgba(179,38,30,.10)}td a{color:var(--unico)}.u{color:var(--unico);font-weight:bold}.d{color:var(--doble);font-weight:bold}
select{background:transparent;color:var(--texto);border:1px solid var(--borde);border-radius:4px}
</style></head><body>
<header><h1>Sentidos de circulación según OpenStreetMap — __TITULO__</h1>
<p>__RESUMEN__ Azul: mano única (la flecha indica hacia dónde se circula). Verde: doble mano.
Tocá un tramo o una fila para verlo; los enlaces abren Google Maps y Street View en ese punto, orientados en el sentido del tramo.
Si un tramo no coincide con la realidad, marcalo, elegí el sentido correcto y descargá el archivo de correcciones.</p></header>
<div id="mapa"></div>
<div class="barra"><input type="search" id="filtro" placeholder="Filtrar por calle o transversal…">
<span id="cuenta"></span><button id="exportar">Descargar sentidos_corregidos.csv</button></div>
<div class="tabla"><table><thead><tr><th>#</th><th>Calle</th><th>Desde</th><th>Hasta</th><th>OSM</th><th>Hacia</th><th>Ver</th><th>¿No coincide?</th><th>Sentido real</th></tr></thead><tbody id="filas"></tbody></table></div>
<script>
const T = __DATOS__;
const mapa = L.map('mapa');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 20,
  attribution: '&copy; colaboradores de OpenStreetMap'}).addTo(mapa);
let guardado = {}; try { guardado = JSON.parse(localStorage.getItem('sentidos___CLAVE__') || '{}'); } catch (e) {}
const capas = {}, grupo = [];
for (const t of T) {
  const color = t.sentido === 'doble' ? 'var(--doble)' : 'var(--unico)';
  const col = t.sentido === 'doble' ? '#4f8a5b' : '#2f5d7c';
  const linea = L.polyline(t.linea, {color: col, weight: 4, opacity: .85}).addTo(mapa);
  if (t.sentido !== 'doble') L.polylineDecorator(linea, {patterns: [{offset: '55%', repeat: 0,
    symbol: L.Symbol.arrowHead({pixelSize: 11, polygon: true, pathOptions: {color: col, fillOpacity: 1, weight: 0}})}]}).addTo(mapa);
  linea.bindPopup(`<b>${t.calle}</b><br>entre ${t.desde}<br>y ${t.hasta}<br>${t.sentido === 'doble' ? 'Doble mano' : 'Mano única, hacia el ' + t.hacia}` +
    `<br><a href="${t.google_maps}" target="_blank" rel="noopener">Google Maps</a> · <a href="${t.street_view}" target="_blank" rel="noopener">Street View</a>`);
  capas[t.id] = linea; grupo.push(linea);
}
mapa.fitBounds(L.featureGroup(grupo).getBounds().pad(.03));
const cuerpo = document.getElementById('filas');
function dibujar() {
  const q = document.getElementById('filtro').value.toLowerCase();
  cuerpo.innerHTML = ''; let n = 0;
  for (const t of T) {
    if (q && !(t.calle + ' ' + t.desde + ' ' + t.hasta).toLowerCase().includes(q)) continue;
    n++; const g = guardado[t.id] || {};
    const tr = document.createElement('tr'); if (g.malo) tr.className = 'marcado';
    tr.innerHTML = `<td>${t.id}</td><td>${t.calle}</td><td>${t.desde}</td><td>${t.hasta}</td>` +
      `<td class="${t.sentido === 'doble' ? 'd' : 'u'}">${t.sentido}</td><td>${t.hacia}</td>` +
      `<td><a href="${t.google_maps}" target="_blank" rel="noopener">Maps</a> · <a href="${t.street_view}" target="_blank" rel="noopener">Street View</a></td>` +
      `<td><input type="checkbox" ${g.malo ? 'checked' : ''}></td>` +
      `<td><select><option value="">—</option><option value="unico" ${g.real === 'unico' ? 'selected' : ''}>mano única</option>` +
      `<option value="doble" ${g.real === 'doble' ? 'selected' : ''}>doble mano</option></select></td>`;
    tr.querySelector('td:nth-child(2)').onclick = () => { mapa.fitBounds(capas[t.id].getBounds().pad(2)); capas[t.id].openPopup(); };
    tr.querySelector('input').onchange = e => { guardar(t.id, {malo: e.target.checked}); tr.className = e.target.checked ? 'marcado' : ''; };
    tr.querySelector('select').onchange = e => guardar(t.id, {real: e.target.value});
    cuerpo.appendChild(tr);
  }
  document.getElementById('cuenta').textContent = n + ' de ' + T.length + ' tramos';
}
function guardar(id, cambio) {
  guardado[id] = Object.assign(guardado[id] || {}, cambio);
  try { localStorage.setItem('sentidos___CLAVE__', JSON.stringify(guardado)); } catch (e) {}
}
document.getElementById('filtro').oninput = dibujar;
document.getElementById('exportar').onclick = () => {
  const porCalle = {};
  for (const t of T) { const g = guardado[t.id]; if (g && g.malo && g.real) porCalle[t.calle] = g.real; }
  const lineas = ['# Correcciones al sentido de circulación (auditoría manual)', 'nombre_calle,sentido']
    .concat(Object.entries(porCalle).map(([c, s]) => `${c},${s}`));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lineas.join('\n') + '\n'], {type: 'text/csv'}));
  a.download = 'sentidos_corregidos.csv'; a.click();
};
dibujar();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Auditoría del sentido de circulación")
    p.add_argument("--area", default="encarnacion", choices=list(CFG["areas"]))
    args = p.parse_args()
    a = cfg_area(args.area)
    titulo = a["nombre"].split(",")[0].strip()
    ciudad = titulo.lower().replace(" ", "_")

    G = gr.construir(a)
    corr = gr.aplicar_correcciones_sentido(G)
    filas = tramos(G, a["epsg_metrico"])
    n_uni = sum(1 for f in filas if f["sentido"] == "único")
    n_dob = len(filas) - n_uni
    resumen = (f"{len(filas)} tramos: {n_uni} de mano única y {n_dob} de doble mano. "
               f"Red de OpenStreetMap descargada el 03/09/2026; correcciones aplicadas: {corr['reglas']}.")

    ruta_csv = RES_MAPAS / f"sentidos_{ciudad}.csv"
    with open(ruta_csv, "w", encoding="utf-8-sig", newline="") as fh:
        campos = ["id", "calle", "desde", "hasta", "sentido", "hacia", "rumbo", "tipo_via", "longitud_m",
                  "lat", "lon", "google_maps", "street_view"]
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(filas)

    pagina = (PAGINA.replace("__TITULO__", html.escape(titulo)).replace("__RESUMEN__", html.escape(resumen))
              .replace("__CLAVE__", ciudad).replace("__DATOS__", json.dumps(filas, ensure_ascii=False)))
    ruta_html = RES_MAPAS / f"sentidos_{ciudad}.html"
    ruta_html.write_text(pagina, encoding="utf-8")
    print(f"== {titulo}: {resumen}")
    print(f"   -> {ruta_html.name}, {ruta_csv.name}")


if __name__ == "__main__":
    main()
