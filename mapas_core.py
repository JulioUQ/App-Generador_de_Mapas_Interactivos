# -*- coding: utf-8 -*-
"""
mapas_core.py
Pegamento entre los módulos existentes y la interfaz web:

  geo_functions.py            -> capas corporativas (GSA, ZEE, FAO, Países)
  generar_mapa_asistente.py   -> motor que construye el HTML (build_map)
  folium_functions.py         -> sigue disponible para scripts; aquí se reutiliza su
                                 aspecto visual (colores de GSA/ZEE/FAO/Países)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from copy import deepcopy
from pathlib import Path

import geopandas as gpd

import generar_mapa_asistente as eng
import geo_functions as gf

# Shapefile al que le falta el .shx: GDAL lo reconstruye a partir del .shp
os.environ.setdefault("SHAPE_RESTORE_SHX", "YES")

# Emojis para el control de capas, agrupados por tipo (como el teclado de WhatsApp).
# Solo emojis de Unicode 12 o anteriores, que se ven bien también en Windows 10.
# Formato: (icono de la pestaña, nombre, emojis separados por espacios)
_EMOJI_DATA = [
    ("🐟", "Mar y pesca",
     "🐟 🐠 🐡 🦈 🐙 🦑 🦐 🦞 🦀 🐚 🐬 🐳 🐋 🐢 🎣 ⚓ 🚢 ⛵ 🛥️ 🚤 ⛴️ 🛶 🧭 🗺️ 🌊 🌐 📍 📌 🔱 🏝️ 🏖️ 🌅 🏭 "
     "☀️ 🌤️ ⛅ 🌧️ ⛈️ 🌬️ 🌫️ ❄️"),
    ("😀", "Caras y personas",
     "😀 😃 😄 😁 😆 😅 😂 🤣 😊 😇 🙂 🙃 😉 😌 😍 🥰 😘 😋 😛 😜 🤪 😎 🤓 🧐 🤔 🤨 😐 😑 😶 🙄 😏 😬 😮 😯 😲 😳 "
     "😢 😭 😱 😖 😞 😤 😡 😠 🥵 🥶 😴 🤒 🤕 🤢 🥳 🤠 👍 👎 👌 ✌️ 🤞 👏 🙌 🙏 💪 👀 👤 👥 👷 🧑"),
    ("🐶", "Animales y naturaleza",
     "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🐤 🦆 🦅 🦉 🦇 🐺 🐗 🐴 🦄 🐝 🐛 🦋 🐌 🐞 🐜 🐍 🦎 🦖 "
     "🐊 🐘 🦒 🌵 🎄 🌲 🌳 🌴 🌱 🌿 🍀 🍁 🍂 🌸 🌹 🌻 🌼 🌍 🌎 🌏 🌙 🌈 🔥 💧"),
    ("🍔", "Comida y bebida",
     "🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🍒 🍑 🍍 🥝 🍅 🥑 🥕 🌽 🌶️ 🥔 🍞 🧀 🥚 🍳 🥞 🥓 🥩 🍗 🍖 🌭 🍔 🍟 🍕 🌮 🌯 🥗 🍝 "
     "🍜 🍲 🍣 🍤 🍙 🍚 🍛 🍦 🍩 🍪 🎂 🍰 🍫 🍬 🍭 ☕ 🍵 🍺 🍷 🥂 🍾 🥛 🧃"),
    ("⚽", "Actividades",
     "⚽ 🏀 🏈 ⚾ 🎾 🏐 🏉 🎱 🏓 🏸 🥅 ⛳ 🏹 🎣 🥊 🥋 ⛸️ 🎿 🏂 🏋️ 🤸 🚴 🏆 🥇 🥈 🥉 🏅 🎖️ 🎯 🎮 🎲 🧩 🎨 🎬 🎤 "
     "🎧 🎸 🎹 🥁 🎻 🎭"),
    ("🚗", "Viajes y lugares",
     "🚗 🚕 🚌 🚎 🏎️ 🚓 🚑 🚒 🚚 🚜 🚲 🛵 🏍️ 🚂 🚆 🚇 ✈️ 🛫 🛬 🚁 🚀 🛸 ⛵ 🚤 🛥️ 🚢 ⚓ ⛽ 🚧 🚦 🗺️ 🗽 🗼 "
     "🏰 🏯 🏟️ 🎡 🎢 🏠 🏡 🏢 🏥 🏦 🏨 🏪 🏫 🏭 ⛪ 🕌 ⛩️ 🌋 🏔️ ⛰️ 🏕️ 🏖️ 🏜️ 🏝️ 🌅 🌄 🌆 🌉"),
    ("💡", "Objetos",
     "⌚ 📱 💻 🖥️ 🖨️ 🕹️ 💾 💿 📷 📹 🎥 📞 📺 📻 🎙️ ⏰ ⏳ 🔋 🔌 💡 🔦 🕯️ 💰 💵 💶 💳 ⚖️ 🔧 🔨 ⚒️ 🛠️ ⛏️ "
     "🔩 ⚙️ 🧰 🧲 🔬 🔭 📡 💉 💊 🩺 🔑 🗝️ 🚪 📦 📫 ✉️ 📝 📁 📂 📅 📊 📈 📉 📋 📎 📏 📐 ✂️ 🗑️ 🔒 🔓 🔍 🔎 🏷️ 📢 🔔"),
    ("🔣", "Símbolos",
     "🔴 🟠 🟡 🟢 🔵 🟣 🟤 ⚫ ⚪ 🟥 🟧 🟨 🟩 🟦 🟪 🟫 ⬛ ⬜ 🔶 🔷 🔸 🔹 🔺 🔻 💠 🔘 ⭕ ❌ ✅ ✔️ ❎ ❗ ❓ ⚠️ "
     "⛔ 🚫 ➕ ➖ ➗ ✖️ ♻️ ➡️ ⬅️ ⬆️ ⬇️ ↗️ ↘️ ↙️ ↖️ ↔️ ↕️ 🔄 🔁 ▶️ ⏸️ ⏹️ ⭐ 🌟 ✨ 💥 💯 ❤️ 🧡 💛 💚 💙 💜 🖤 🤍 "
     "🤎 💔 🆕 🆗 🆒 🆓 ℹ️ 🅿️ 🔰 🏁 🚩 🏴 🏳️"),
]
EMOJI_CATEGORIAS: list[tuple[str, str, list[str]]] = [
    (icono, nombre, list(dict.fromkeys(lista.split()))) for icono, nombre, lista in _EMOJI_DATA
]

# ---------------------------------------------------------------------------
# Capas corporativas de referencia (mismo estilo que folium_functions.generar_mapa_base)
# Orden = orden de dibujo, de abajo a arriba.
# ---------------------------------------------------------------------------
REFERENCIAS: dict[str, dict] = {
    "gsa": {
        "label": "Zonas GSA (Mediterráneo)", "loader": "gdf_gsa", "default": True,
        "lcfg": {"name": "GSA", "show": True, "style": {"mode": "single", "color": "#808000"},
                 "weight": 1, "fill_opacity": 0.4, "tooltip": ["NombreGSA"], "popup": [],
                 "simplify": 0.002},
    },
    "zee": {
        "label": "Zonas Económicas Exclusivas (ZEE)", "loader": "gdf_ZEE", "default": False,
        "lcfg": {"name": "ZEE", "show": True, "style": {"mode": "single", "color": "#d62728"},
                 "weight": 1, "dashed": True, "fill_opacity": 0, "tooltip": [], "popup": [],
                 "simplify": 0.005},
    },
    "fao": {
        "label": "Zonas FAO", "loader": "gdf_FAO", "default": False,
        "lcfg": {"name": "FAO", "show": True, "style": {"mode": "single", "color": "#0066cc"},
                 "weight": 1.5, "fill_opacity": 0, "tooltip": ["Zona"], "popup": [],
                 "simplify": 0.005},
    },
    "paises": {
        "label": "Países (máscara de tierra)", "loader": "gdf_paises", "default": False,
        "lcfg": {"name": "Países", "show": True, "style": {"mode": "single", "color": "#e3e3e3"},
                 "weight": 0.5, "fill_opacity": 1.0, "tooltip": [], "popup": [],
                 "simplify": 0.01, "on_top": True},      # única capa que va por encima de los puntos
    },
}


def set_gis_dir(path: str | None) -> None:
    """Cambia la carpeta de capas corporativas (sin tocar geo_functions.py)."""
    if path:
        gf.GIS_DIR = Path(path)


def gis_dir() -> Path:
    return Path(gf.GIS_DIR)


def cargar_referencia(clave: str) -> gpd.GeoDataFrame:
    """Carga una capa corporativa usando geo_functions. Lanza FileNotFoundError/Exception si no se puede."""
    gdf = getattr(gf, REFERENCIAS[clave]["loader"])()
    return eng.finish_vector(gdf, "EPSG:4326")


def lcfg_referencia(clave: str, show: bool = True) -> dict:
    """`show`: si la capa arranca activa en el control de capas (la elige el usuario)."""
    lcfg = deepcopy(REFERENCIAS[clave]["lcfg"])
    lcfg["path"] = f"corporativa:{clave}"
    lcfg["reference"] = True          # va al apartado «Capas geográficas auxiliares» de la leyenda
    lcfg["show"] = bool(show)
    return lcfg


# ---------------------------------------------------------------------------
# Subidas de archivos
# ---------------------------------------------------------------------------
def _extraer_zip(zpath: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    base = destino.resolve()
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            target = (destino / info.filename).resolve()
            if base not in target.parents and target != base:  # evita rutas fuera de la carpeta
                raise eng.ConfigError("El ZIP contiene rutas no permitidas.")
        z.extractall(destino)


def guardar_subidas(archivos: list[tuple[str, bytes]], destino: Path) -> list[Path]:
    """
    Guarda los archivos subidos (juntos, para que .shp/.dbf/.shx/.prj convivan) y
    devuelve las capas vectoriales encontradas. Los .zip se descomprimen.
    Solo escribe lo que ha cambiado y elimina lo que el usuario ya no tiene subido.
    """
    destino.mkdir(parents=True, exist_ok=True)
    nombres, stems_shp, carpetas_zip = set(), set(), set()
    for nombre, datos in archivos:
        ruta = destino / Path(nombre).name
        nombres.add(ruta.name)
        if ruta.suffix.lower() == ".shp":
            stems_shp.add(ruta.stem.lower())
        cambio = not ruta.exists() or ruta.stat().st_size != len(datos)
        if cambio:
            ruta.write_bytes(datos)
        if ruta.suffix.lower() == ".zip":
            carpetas_zip.add(ruta.stem)
            if cambio or not (destino / ruta.stem).exists():
                shutil.rmtree(destino / ruta.stem, ignore_errors=True)
                _extraer_zip(ruta, destino / ruta.stem)
    for item in destino.iterdir():                      # limpiar restos de subidas anteriores
        if item.is_dir() and item.name not in carpetas_zip:
            shutil.rmtree(item, ignore_errors=True)
        elif item.is_file() and item.name not in nombres and item.stem.lower() not in stems_shp:
            item.unlink(missing_ok=True)                # (los .shx reconstruidos se conservan)
    encontrados = [p for p in destino.rglob("*")
                   if p.is_file() and p.suffix.lower() in eng.VECTOR_EXT]
    return sorted(encontrados)


# ---------------------------------------------------------------------------
# Capas elegidas desde el disco (detecta solas los archivos que acompañan al .shp)
# ---------------------------------------------------------------------------
# El selector de archivos del navegador solo entrega los archivos marcados y nunca la carpeta de
# origen. Como la aplicación corre en el propio ordenador del usuario, se abre el selector del
# sistema desde Python: así se conoce la ruta real y se recogen todos los archivos del shapefile.
SHAPEFILE_EXT = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx", ".qix",
                 ".fix", ".atx", ".ixs", ".mxs"}
_TIPOS_CAPA = [("Capas (shp, gpkg, geojson, kml, gml, fgb, zip)",
                ["*.shp", "*.gpkg", "*.geojson", "*.json", "*.kml", "*.gml", "*.fgb", "*.zip"]),
               ("Todos los archivos", ["*.*"])]

_DIALOGO_PY = r"""
import json, sys
import tkinter as tk
from tkinter import filedialog
titulo, inicial, tipos = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)   # que la ventana salga delante del navegador
    root.lift()
    root.focus_force()
except Exception:
    pass
kw = {"initialdir": inicial} if inicial else {}
rutas = filedialog.askopenfilenames(parent=root, title=titulo,
                                    filetypes=[(n, tuple(p)) for n, p in tipos], **kw)
root.destroy()
print(json.dumps(list(rutas)))
"""


def elegir_capas_del_disco(inicial: str | None = None) -> list[Path]:
    """
    Abre el selector de archivos del sistema y devuelve las rutas elegidas ([] si cancela).
    Se ejecuta en un proceso aparte porque tkinter no convive bien con los hilos de Streamlit.
    Lanza RuntimeError si no hay entorno gráfico o falta tkinter.
    """
    inicial = inicial if inicial and Path(inicial).is_dir() else ""
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        res = subprocess.run(
            [sys.executable, "-c", _DIALOGO_PY, "Elige las capas (puedes marcar varias)", inicial,
             json.dumps(_TIPOS_CAPA)],
            capture_output=True, text=True, encoding="utf-8", timeout=900, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Se agotó el tiempo de espera del selector de archivos.") from exc
    if res.returncode != 0:
        detalle = (res.stderr or "").strip().splitlines()
        raise RuntimeError(detalle[-1] if detalle else "No se pudo abrir el selector de archivos.")
    try:
        return [Path(r) for r in json.loads(res.stdout.strip().splitlines()[-1])]
    except (ValueError, IndexError):
        return []


def acompanantes(shp: Path) -> list[Path]:
    """Todos los archivos del shapefile (.dbf, .prj, .cpg, .shx…) que están junto al .shp."""
    shp = Path(shp)
    return sorted(f for f in shp.parent.iterdir()
                  if f.is_file() and f.stem.lower() == shp.stem.lower()
                  and f.suffix.lower() in SHAPEFILE_EXT)


def _origenes(rutas: list[Path | str]) -> list[Path]:
    """Archivos que hay que copiar para las rutas elegidas (un .shp arrastra a sus acompañantes)."""
    out: list[Path] = []
    for r in map(Path, rutas):
        if not r.is_file():
            continue
        out.extend(acompanantes(r) if r.suffix.lower() == ".shp" else [r])
    return list(dict.fromkeys(out))


def firma_disco(rutas: list[Path | str]) -> tuple:
    """Cambia si el usuario elige otras capas o si se modifica alguno de sus archivos en disco."""
    firma = []
    for f in _origenes(rutas):
        st = f.stat()
        firma.append((str(f), st.st_size, st.st_mtime_ns))
    return tuple(firma)


def importar_desde_disco(rutas: list[Path | str], destino: Path) -> list[Path]:
    """
    Copia a la carpeta de trabajo las capas elegidas (cada .shp con TODOS sus acompañantes) y
    devuelve las capas vectoriales encontradas. No toca la carpeta original (GDAL puede querer
    reconstruir el .shx y allí podría no tener permiso de escritura). Solo copia lo que cambió.
    """
    destino.mkdir(parents=True, exist_ok=True)
    esperados: set[Path] = set()
    carpetas_zip: set[Path] = set()
    stems_shp: set[tuple[Path, str]] = set()
    for origen in _origenes(rutas):
        sub = destino / hashlib.md5(str(origen.parent).lower().encode("utf-8", "ignore")).hexdigest()[:8]
        sub.mkdir(parents=True, exist_ok=True)
        dest = sub / origen.name
        esperados.add(dest)
        if origen.suffix.lower() == ".shp":
            stems_shp.add((sub, origen.stem.lower()))
        cambio = (not dest.exists() or dest.stat().st_size != origen.stat().st_size
                  or dest.stat().st_mtime_ns // 1_000_000_000 != origen.stat().st_mtime_ns // 1_000_000_000)
        if cambio:
            shutil.copy2(origen, dest)
        if origen.suffix.lower() == ".zip":
            zdir = sub / origen.stem
            carpetas_zip.add(zdir)
            if cambio or not zdir.exists():
                shutil.rmtree(zdir, ignore_errors=True)
                _extraer_zip(dest, zdir)
    for item in sorted(destino.rglob("*"), reverse=True):   # limpiar lo que ya no está elegido
        if not item.exists():
            continue
        if any(z == item or z in item.parents for z in carpetas_zip):
            continue
        if item.is_file():
            if item in esperados or (item.parent, item.stem.lower()) in stems_shp:
                continue                                    # (los .shx reconstruidos se conservan)
            item.unlink(missing_ok=True)
        elif item.is_dir() and not any(item.iterdir()):
            item.rmdir()
    return sorted(p for p in destino.rglob("*") if p.is_file() and p.suffix.lower() in eng.VECTOR_EXT)


def huella(path: Path) -> str:
    """
    Identifica el CONTENIDO de una capa: el archivo y, en un shapefile, todos sus acompañantes
    (.dbf, .prj, .cpg…). Si llega un acompañante después, la huella cambia y la capa se vuelve a leer.
    El .shx se excluye: GDAL puede reconstruirlo y no aporta atributos ni coordenadas.
    """
    path = Path(path)
    if path.suffix.lower() == ".shp":
        partes = [f for f in path.parent.iterdir()
                  if f.is_file() and f.stem.lower() == path.stem.lower() and f.suffix.lower() != ".shx"]
    else:
        partes = [path]
    return "|".join(f"{f.suffix.lower()}:{f.stat().st_size}:{f.stat().st_mtime_ns}"
                    for f in sorted(partes, key=lambda f: f.suffix.lower()))


def archivos_que_faltan(shp: Path) -> list[str]:
    """Extensiones de acompañamiento que no están junto a un .shp (comparación sin mayúsculas)."""
    if shp.suffix.lower() != ".shp":
        return []
    presentes = {f.suffix.lower() for f in shp.parent.iterdir() if f.stem.lower() == shp.stem.lower()}
    return [e for e in (".dbf", ".shx", ".prj") if e not in presentes]


def guardar_archivo(nombre: str, datos: bytes, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / Path(nombre).name
    ruta.write_bytes(datos)
    return ruta


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------
def generar_mapa(cfg: dict, cache: dict) -> Path:
    cfg = dict(cfg)
    cfg["open_browser"] = False
    return eng.build_map(cfg, cache)
