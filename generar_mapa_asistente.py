#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asistente para generar mapas interactivos (Folium / Leaflet)
============================================================

Genera un único HTML autocontenido a partir de:
  * un dataset de POSICIONES (Excel, CSV, Parquet o puntos en GPKG/SHP/GeoJSON), y
  * cero o más capas de POLÍGONOS / LÍNEAS / PUNTOS (SHP, GPKG, GeoJSON...).

Uso
---
    python generar_mapa_asistente.py
        Modo asistente: abre el explorador de archivos y hace las preguntas por consola.
        Al terminar guarda tus respuestas en  <mapa>.config.json

    python generar_mapa_asistente.py --config mapa.config.json
        Regenera el mapa sin preguntar nada.

    python generar_mapa_asistente.py --config mapa.config.json --posiciones datos_nuevos.xlsx
        Igual, pero sustituyendo el dataset de posiciones (datos futuros con la misma estructura).

Opciones: --salida RUTA.html · --sin-dialogos (pide rutas escritas) · --no-abrir

Qué se puede personalizar desde el asistente
--------------------------------------------
  * Colorear posiciones y capas: un color, por categorías de una columna o por rangos
    de una columna numérica. Cada categoría es una capa independiente en el control de capas.
  * Campos del tooltip y del popup.
  * Selectores tipo Power BI (multiselección con búsqueda) sobre cualquier columna de las
    posiciones y filtro por rango de fechas.
  * Tamaño de los puntos, opacidad de relleno, grosor y trazo discontinuo de las capas,
    simplificación de geometrías, título, subtítulo y logo opcionales.

Dependencias: folium, geopandas, pandas, numpy, openpyxl (Excel). tkinter es opcional.
"""
from __future__ import annotations

import argparse
import base64
import colorsys
import csv
import json
import logging
import math
import mimetypes
import os
import re
import shutil
import sys
import webbrowser
from html import escape
from pathlib import Path
from typing import Any, Optional

import folium
from folium.map import CustomPane
import geopandas as gpd
import numpy as np
import pandas as pd
from branca.element import MacroElement
from folium import Element, FeatureGroup
from folium.plugins import MiniMap, MousePosition
from jinja2 import Template

# ============================================================================
# 1. AJUSTES VISUALES (el resto lo decide el asistente)
# ============================================================================
CONFIG_VERSION = 1
TARGET_CRS = "EPSG:4326"
ASSUMED_CRS_IF_MISSING = "EPSG:4326"

DEFAULT_POINT_RADIUS = 2.6             # px
POINT_FILL_OPACITY = 0.72
POINT_STROKE_COLOR = "#ffffff"         # borde fino de cada punto (0 en grosor = sin borde)
POINT_STROKE_WEIGHT = 0.5
POINT_STROKE_OPACITY = 0.55

EXTRA_BASEMAPS = True                  # añade OpenStreetMap y Esri World Imagery como bases alternativas
BRAND_BLUE = "#0a5ca8"                 # acento principal: títulos, enlaces, botón activo
BRAND_GREEN = "#7ab51d"
BRAND_ORANGE = "#f08a00"               # rectángulo del minimapa y del zoom a un área
UI_FONT = ('"Inter", "Segoe UI", system-ui, -apple-system, Roboto, '
           '"Helvetica Neue", Arial, sans-serif')
BASEMAP_FILTER = "saturate(0.55) brightness(1.05) contrast(0.92)"
BASEMAP_CLASS = "basemap-ocean"
FIT_PADDING = (50, 50)                 # margen de la vista inicial (px)

# Avisos del asistente
MAX_POINTS_WARNING = 250_000
MAX_CATEGORIES_WARNING = 40
MAX_SLICER_VALUES_WARNING = 1000
SIMPLIFY_SUGGEST_VERTICES = 300_000

# Paletas
CATEGORY_PALETTE = ["#0b4a9e", "#d02a3c", "#2a9d8f", "#f4a261", "#7b2cbf", "#8d6e63",
                    "#e9c46a", "#264653", "#e76f51", "#43aa8b", "#577590", "#b5179e"]
RAMPS: dict[str, list[str]] = {
    "amarillo-rojo": ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"],
    "azules": ["#eff3ff", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#084594"],
    "viridis": ["#440154", "#443983", "#31688e", "#21908d", "#35b779", "#8fd744", "#fde725"],
    "azul-rojo": ["#4575b4", "#91bfdb", "#e0f3f8", "#ffffbf", "#fee090", "#fc8d59", "#d73027"],
}
COLOR_NAMES = {
    "rojo": "#d02a3c", "azul": "#0b4a9e", "verde": "#2a9d4f", "naranja": "#f08a00",
    "morado": "#7b2cbf", "violeta": "#7b2cbf", "amarillo": "#f2c200", "gris": "#7f8c8d",
    "negro": "#222222", "blanco": "#ffffff", "marron": "#7b4f3a", "marrón": "#7b4f3a",
    "rosa": "#e0529c", "turquesa": "#1aa6a6", "celeste": "#4fb3e8",
}
NO_VALUE = "—"
EPOCH = pd.Timestamp("1970-01-01")

TABULAR_EXT = {".csv", ".txt", ".tsv", ".xlsx", ".xlsm", ".xls", ".parquet"}
VECTOR_EXT = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gml", ".fgb"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("mapa_asistente")


class ConfigError(Exception):
    """Error de configuración/datos con un mensaje pensado para el usuario."""


class UserAbort(Exception):
    """El usuario ha cancelado el asistente."""


# ============================================================================
# 2. COLORES
# ============================================================================
def normalize_color(text: str) -> Optional[str]:
    """Acepta '#RRGGBB', 'RRGGBB', '#RGB' o un nombre en español. Devuelve '#rrggbb' o None."""
    t = text.strip().lower()
    if t in COLOR_NAMES:
        return COLOR_NAMES[t]
    t = t.lstrip("#")
    if re.fullmatch(r"[0-9a-f]{3}", t):
        t = "".join(ch * 2 for ch in t)
    if re.fullmatch(r"[0-9a-f]{6}", t):
        return "#" + t
    return None


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def ramp(name: str, n: int) -> list[str]:
    """n colores interpolados a lo largo de una rampa secuencial/divergente."""
    base = RAMPS.get(name, RAMPS["amarillo-rojo"])
    if n <= 1:
        return [base[len(base) // 2]]
    out = []
    for i in range(n):
        x = i * (len(base) - 1) / (n - 1)
        lo = int(math.floor(x))
        hi = min(lo + 1, len(base) - 1)
        f = x - lo
        a, b = _hex_to_rgb(base[lo]), _hex_to_rgb(base[hi])
        out.append(_rgb_to_hex(tuple(a[k] + (b[k] - a[k]) * f for k in range(3))))
    return out


def _palette_iter():
    yield from CATEGORY_PALETTE
    i = 1
    while True:                      # más de 12 categorías: tonos repartidos por la razón áurea
        r, g, b = colorsys.hls_to_rgb((i * 0.618034) % 1.0, 0.45, 0.62)
        yield _rgb_to_hex((r * 255, g * 255, b * 255))
        i += 1


def assign_colors(cats: list[str], saved: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Respeta los colores guardados; las categorías nuevas reciben colores aún no usados."""
    saved = saved or {}
    out = {c: saved[c] for c in cats if c in saved}
    used = set(out.values())
    pool = (c for c in _palette_iter() if c not in used)
    for c in cats:
        if c not in out:
            out[c] = next(pool)
    return out


# ============================================================================
# 3. TEXTO, TIPOS Y LECTURA DE DATOS
# ============================================================================
def clean_text(s: pd.Series) -> pd.Series:
    """Serie de texto limpio para mostrar/agrupar (nulos -> '—', '4.0' -> '4')."""
    if pd.api.types.is_datetime64_any_dtype(s):
        has_time = bool(s.notna().any() and (s.dt.normalize() != s).any())
        out = s.dt.strftime("%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d").astype("string")
    else:
        out = s.astype("string")
    out = out.str.strip().str.replace(r"\.0$", "", regex=True)
    return out.fillna(NO_VALUE).replace("", NO_VALUE).astype(object)


def column_kind(s: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(s):
        return "fecha"
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return "número"
    return "texto"


def visible_columns(df: pd.DataFrame) -> list[str]:
    geom = getattr(df, "geometry", None)
    gname = geom.name if geom is not None else None
    return [c for c in df.columns if not str(c).startswith("__") and c != gname]


def to_float(s: pd.Series) -> pd.Series:
    """A número, aceptando coma decimal ('36,5')."""
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        s = s.astype(str).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def to_datetime_flex(s: pd.Series) -> pd.Series:
    """A fecha sin zona horaria; si el formato día/mes es ambiguo, elige el que parsea más filas."""
    if not pd.api.types.is_datetime64_any_dtype(s):
        a = pd.to_datetime(s, errors="coerce")
        b = pd.to_datetime(s, errors="coerce", dayfirst=True)
        s = b if b.notna().sum() > a.notna().sum() else a
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_convert("UTC").dt.tz_localize(None)
    return s


def coerce_decimal_comma_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas de texto con números tipo '12,5' (típico de CSV europeo) -> numéricas."""
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            sample = df[c].dropna().astype(str).head(1000)
            if len(sample) and sample.str.fullmatch(r"-?\d+,\d+").mean() >= 0.9:
                df[c] = to_float(df[c])
    return df


def _read_csv_flex(path: Path) -> pd.DataFrame:
    last: Optional[Exception] = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=enc, newline="") as fh:
                sample = fh.read(8192)
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                sep = ","
            return pd.read_csv(path, sep=sep, encoding=enc, low_memory=False)
        except UnicodeDecodeError as exc:
            last = exc
    raise ConfigError(f"No se pudo leer el CSV (codificación no reconocida): {last}")


def read_vector_raw(path: Path, layer: Optional[str] = None) -> gpd.GeoDataFrame:
    if not Path(path).is_file():
        raise ConfigError(f"No existe el archivo: {path}")
    # Si a un shapefile le falta el .shx, GDAL lo reconstruye a partir del .shp
    os.environ.setdefault("SHAPE_RESTORE_SHX", "YES")
    return gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)


def finish_vector(gdf: gpd.GeoDataFrame, assumed_crs: Optional[str]) -> gpd.GeoDataFrame:
    """Reproyecta a EPSG:4326 y descarta geometrías vacías."""
    if gdf.crs is None:
        crs = assumed_crs or ASSUMED_CRS_IF_MISSING
        log.warning("Capa sin CRS definido; se asume %s.", crs)
        gdf = gdf.set_crs(crs)
    gdf = gdf.to_crs(TARGET_CRS)
    gdf = gdf[~(gdf.geometry.isna() | gdf.geometry.is_empty)]
    return gdf.reset_index(drop=True)


def _excel_engine() -> Optional[str]:
    """'calamine' (6-10x más rápido que openpyxl) si está instalado; si no, el motor por defecto."""
    try:
        import python_calamine  # noqa: F401
        return "calamine"
    except ImportError:
        return None


def list_sheets(path: Path) -> list[str]:
    for engine in (_excel_engine(), None):
        try:
            return [str(s) for s in pd.ExcelFile(path, engine=engine).sheet_names]
        except Exception:  # noqa: BLE001 - si calamine falla, se reintenta con el motor por defecto
            if engine is None:
                raise
    return []


def _read_excel(path: Path, sheet: str) -> pd.DataFrame:
    engine = _excel_engine()
    if engine:
        try:
            return pd.read_excel(path, sheet_name=sheet, engine=engine)
        except Exception as exc:  # noqa: BLE001
            log.warning("Lectura rápida de Excel no disponible (%s); se usa el motor estándar.", exc)
    return pd.read_excel(path, sheet_name=sheet)


def list_vector_layers(path: Path) -> list[str]:
    try:
        import pyogrio
        return [str(r[0]) for r in pyogrio.list_layers(path)]
    except Exception:  # noqa: BLE001
        try:
            import fiona
            return list(fiona.listlayers(str(path)))
        except Exception:  # noqa: BLE001
            return []


def read_table(path: Path, sheet: Optional[str] = None) -> pd.DataFrame:
    """Lee un dataset tabular (o un vector de puntos, del que extrae lon/lat)."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"No existe el archivo de posiciones: {path}")
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        names = list_sheets(path)
        if sheet and sheet not in names:
            log.warning("La hoja '%s' no existe en %s; se usa '%s'.", sheet, path.name, names[0])
            sheet = None
        df = _read_excel(path, sheet or names[0])
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    elif ext in (".csv", ".txt", ".tsv"):
        df = _read_csv_flex(path)
    elif ext in VECTOR_EXT:
        gdf = finish_vector(read_vector_raw(path), None)
        if not gdf.geom_type.isin(["Point"]).all():
            raise ConfigError("El dataset de posiciones debe contener sólo puntos.")
        df = pd.DataFrame(gdf.drop(columns=gdf.geometry.name))
        df["lon_geom"], df["lat_geom"] = gdf.geometry.x.values, gdf.geometry.y.values
    else:
        raise ConfigError(f"Formato no soportado: {ext}")
    df.columns = [str(c).strip() for c in df.columns]
    return coerce_decimal_comma_columns(df)


def guess_column(df: pd.DataFrame, exact: tuple[str, ...], contains: tuple[str, ...]) -> Optional[str]:
    cols = visible_columns(df)
    for c in cols:
        if str(c).strip().lower() in exact:
            return c
    for c in cols:
        if any(k in str(c).lower() for k in contains):
            return c
    return None


def guess_lat(df): return guess_column(df, ("latitud", "latitude", "lat", "y", "lat_geom"), ("lat",))
def guess_lon(df): return guess_column(df, ("longitud", "longitude", "lon", "lng", "long", "x", "lon_geom"), ("lon", "lng"))


def guess_date(df: pd.DataFrame) -> Optional[str]:
    cols = visible_columns(df)
    for c in cols:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return c
    for c in cols:
        if (any(k in str(c).lower() for k in ("fecha", "date", "time", "hora", "timestamp"))
                and not pd.api.types.is_numeric_dtype(df[c])):
            return c
    return None


def require_columns(df: pd.DataFrame, needed: list[str], where: str) -> None:
    missing = list(dict.fromkeys(c for c in needed if c and c not in df.columns))
    if missing:
        raise ConfigError(
            f"Faltan columnas en {where}: {missing}\n"
            f"  Columnas disponibles: {visible_columns(df)}\n"
            "  Ejecuta el script sin --config para repetir el asistente con estos datos.")


def prepare_positions(pcfg: dict, raw: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Valida columnas, limpia coordenadas y fechas y (opcional) submuestrea."""
    df = raw.copy() if raw is not None else read_table(Path(pcfg["path"]), pcfg.get("sheet"))
    n_read = len(df)
    used = [pcfg["lat"], pcfg["lon"], pcfg.get("date")]
    for key in ("tooltip", "popup", "slicers"):
        used += list(pcfg.get(key, []))
    if pcfg.get("style", {}).get("column"):
        used.append(pcfg["style"]["column"])
    require_columns(df, used, "el dataset de posiciones")

    df["__lat"] = to_float(df[pcfg["lat"]])
    df["__lon"] = to_float(df[pcfg["lon"]])
    valid = df["__lat"].between(-90, 90) & df["__lon"].between(-180, 180)
    if (~valid).any():
        log.warning("Se descartan %d filas con coordenadas inválidas o vacías.", int((~valid).sum()))
    n_invalid = int((~valid).sum())
    df = df.loc[valid].reset_index(drop=True)
    if df.empty:
        raise ConfigError("El dataset no contiene ninguna posición con coordenadas válidas.")

    if pcfg.get("date"):
        df[pcfg["date"]] = to_datetime_flex(df[pcfg["date"]])
    mx = pcfg.get("max_points")
    if mx and len(df) > mx:
        log.warning("Submuestreo: %d -> %d puntos.", len(df), mx)
        df = df.sample(int(mx), random_state=42).reset_index(drop=True)
    # filas del archivo / descartadas por coordenadas inválidas / finalmente dibujadas
    df.attrs.update({"n_leidas": n_read, "n_invalidas": n_invalid, "n_dibujadas": len(df)})
    return df


def load_vector(lcfg: dict) -> gpd.GeoDataFrame:
    gdf = finish_vector(read_vector_raw(Path(lcfg["path"]), lcfg.get("layer")), lcfg.get("crs_assumed"))
    keep = [lcfg.get("style", {}).get("column")] + list(lcfg.get("tooltip", [])) + list(lcfg.get("popup", []))
    require_columns(gdf, [c for c in keep if c], f"la capa «{lcfg.get('name')}»")
    return gdf


# ============================================================================
# 4. AGRUPACIÓN Y SIMBOLOGÍA (categorías / rangos numéricos)
# ============================================================================
def _fmt_num(x: float) -> str:
    return f"{x:.4g}"


def resolve_groups(df: pd.DataFrame, style: dict) -> tuple[np.ndarray, list[dict]]:
    """
    Devuelve (código de grupo por fila, lista de grupos {label,color,show,n}).
    Cada grupo será una capa independiente en el control de capas.
    """
    mode, col, n = style.get("mode", "single"), style.get("column"), len(df)

    if mode == "category" and col in df.columns:
        txt = clean_text(df[col])
        counts = txt.value_counts()
        cats = [str(c) for c in counts.index]              # más frecuentes primero (abajo)
        colors = assign_colors(cats, style.get("colors"))
        hidden = set(style.get("hidden", []))
        mapping = {c: i for i, c in enumerate(cats)}
        codes = txt.map(mapping).to_numpy()
        groups = [{"label": c, "color": colors[c], "show": c not in hidden, "n": int(counts[c])}
                  for c in cats]
        return codes, groups

    if mode == "numeric" and col in df.columns:
        vals = to_float(df[col])
        k = max(2, min(int(style.get("classes", 5)), 9))
        try:
            bins = pd.qcut(vals, q=k, duplicates="drop")
        except ValueError:
            bins = None
        if bins is not None and len(bins.cat.categories) >= 1:
            cats = list(bins.cat.categories)
            colors = ramp(style.get("palette", "amarillo-rojo"), len(cats))
            lows = [float(vals.min())] + [float(iv.left) for iv in cats[1:]]
            groups = []
            for i, iv in enumerate(cats):
                groups.append({"label": f"{_fmt_num(lows[i])} – {_fmt_num(float(iv.right))}",
                               "color": colors[i], "show": True, "n": int((bins.cat.codes == i).sum())})
            codes = bins.cat.codes.to_numpy().astype(int)
            if (codes < 0).any():
                codes[codes < 0] = len(groups)
                groups.append({"label": "(sin valor)", "color": "#9e9e9e", "show": True,
                               "n": int((codes == len(groups) - 1).sum())})
            return codes, groups
        log.warning("No se pudieron calcular rangos para «%s»; se usa un solo color.", col)

    return (np.zeros(n, dtype=int),
            [{"label": "", "color": style.get("color", "#0b4a9e"), "show": True, "n": n}])


# ============================================================================
# 5. MAPA BASE Y LEYENDA
# ============================================================================
def create_base_map(bounds: list[list[float]]) -> folium.Map:
    center = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
    # zoomSnap/zoomDelta fraccionarios: con el valor por defecto Leaflet redondea el zoom
    # hacia abajo al encuadrar y deja mucho espacio vacío alrededor de los datos.
    m = folium.Map(location=center, zoom_start=5, tiles=None,
                   prefer_canvas=True, control_scale=True, zoom_control=False,
                   zoomSnap=0.25, zoomDelta=0.5)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
        name="Esri World Ocean Base",
        attr="Tiles © Esri — Sources: GEBCO, NOAA, Esri, DeLorme, NAVTEQ, and others",
        control=True, className=BASEMAP_CLASS,
    ).add_to(m)
    if EXTRA_BASEMAPS:
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=True, show=False).add_to(m)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            name="Esri World Imagery",
            attr="Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and others",
            control=True, show=False,
        ).add_to(m)
    m.fit_bounds(bounds, padding=FIT_PADDING, max_zoom=12)
    return m


def _swatch_circle(color: str) -> str:
    return f'<span class="lg-sw lg-circle" style="background:{color};"></span>'


def _swatch_line(color: str, dashed: bool = False, weight: int = 3) -> str:
    style = "dashed" if dashed else "solid"
    return f'<span class="lg-sw lg-line" style="border-top:{weight}px {style} {color};"></span>'


def _swatch_box(fill: str, border: str, dashed: bool = False, opacity: float = 0.33) -> str:
    style = "dashed" if dashed else "solid"
    alpha = format(int(round(max(0.2, min(opacity, 1.0)) * 255)), "02x")
    return (f'<span class="lg-sw lg-box" style="background:{fill}{alpha};'
            f'border:2px {style} {border};"></span>')


def add_legend(m: folium.Map, sections: dict[str, list[str]]) -> None:
    body = ""
    for title, rows in sections.items():
        if rows:
            body += (f"<h4>{escape(title)}</h4>"
                     + "".join(f'<div class="lg-row">{r}</div>' for r in rows))
    root = m.get_root()
    root.header.add_child(Element(_render_page_css()))
    if body:
        root.html.add_child(Element(
            f'<details id="map-legend" open><summary>Leyenda</summary>{body}</details>'))


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _icon(item: dict, swatch: str) -> str:
    """
    Icono ÚNICO de un grupo, el mismo en la leyenda y en el control de capas:
    el emoji que haya elegido el usuario o, si no hay, el símbolo del estilo real (color, trazo…).
    """
    emoji = (item.get("emoji") or "").strip()
    if emoji:
        return f'<span class="lg-sw lg-emoji">{escape(emoji)}</span>'
    return swatch


def _control_name(text: str, icon: str = "") -> str:
    """
    Texto del control de capas: icono (idéntico al de la leyenda) + nombre.
    Leaflet pinta el nombre como HTML, por eso el texto se escapa.
    """
    text = escape(text, quote=False)
    return f"{icon} {text}" if icon else text


REFERENCE_SECTION = "Capas geográficas auxiliares"
TOP_PANE = "capas_aux_encima"      # pane por encima de los puntos (z-index > overlayPane=400)


# ============================================================================
# 6. CAPAS VECTORIALES (polígonos / líneas / puntos)
# ============================================================================
def geometry_kind(gdf: gpd.GeoDataFrame) -> str:
    types = set(gdf.geom_type.dropna().unique())
    if types <= {"Polygon", "MultiPolygon"}:
        return "polygon"
    if types <= {"LineString", "MultiLineString", "LinearRing"}:
        return "line"
    if types <= {"Point", "MultiPoint"}:
        return "point"
    return "mixed"


def _jsonable(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fechas y objetos raros -> texto, para que el GeoJSON se pueda serializar."""
    gdf = gdf.copy()
    for c in gdf.columns:
        if c == gdf.geometry.name:
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[c]):
            gdf[c] = gdf[c].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
        elif pd.api.types.is_object_dtype(gdf[c]):
            gdf[c] = gdf[c].map(lambda v: v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
    return gdf


def layer_style(color: str, lcfg: dict, kind: str) -> dict:
    return {"color": color, "weight": lcfg.get("weight", 2),
            "opacity": 0.95, "fillColor": color,
            "fillOpacity": lcfg.get("fill_opacity", 0.3) if kind != "line" else 0,
            "dashArray": "6 4" if lcfg.get("dashed") else None}


def add_vector_layer(m: folium.Map, gdf: gpd.GeoDataFrame, lcfg: dict) -> list[str]:
    """Una FeatureGroup por categoría/rango, para activarlas por separado en el control de capas."""
    gdf = gdf.copy()
    tol = lcfg.get("simplify")
    if tol:
        gdf["geometry"] = gdf.geometry.simplify(float(tol), preserve_topology=True)
    style = lcfg.get("style", {})
    tip = [c for c in lcfg.get("tooltip", []) if c in gdf.columns]
    pop = [c for c in lcfg.get("popup", []) if c in gdf.columns]
    keep = list(dict.fromkeys(tip + pop + ([style["column"]] if style.get("column") in gdf.columns else [])))
    codes, groups = resolve_groups(gdf, style)
    kind = geometry_kind(gdf)
    rows: list[str] = []

    for gi, g in enumerate(groups):
        mask = codes == gi
        if not mask.any():
            continue
        sub = _jsonable(gdf.loc[mask, keep + [gdf.geometry.name]])
        st = layer_style(g["color"], lcfg, kind)
        name = lcfg["name"] if not g["label"] else f"{lcfg['name']} · {g['label']}"
        is_ref = bool(lcfg.get("reference"))
        if kind == "line":
            sw = _swatch_line(g["color"], bool(lcfg.get("dashed")), 3)
        elif kind == "point":
            sw = _swatch_circle(g["color"])
        else:
            sw = _swatch_box(g["color"], g["color"], bool(lcfg.get("dashed")), st["fillOpacity"])
        icon = _icon(lcfg, sw)          # el mismo icono en el control de capas y en la leyenda
        # Las capas auxiliares también van al control de capas; el usuario decide cuáles abren activas.
        # Sin contador en el nombre: en una capa auxiliar el nº de polígonos no aporta nada.
        ctrl_txt = name if is_ref else f"{name} ({_fmt_int(int(mask.sum()))})"
        fg = FeatureGroup(name=_control_name(ctrl_txt, icon),
                          show=bool(lcfg.get("show", True)) and g["show"])
        extra = {"pane": TOP_PANE} if lcfg.get("on_top") else {}   # p. ej. Países: por encima de los puntos
        folium.GeoJson(
            sub,
            style_function=lambda _f, st=st: st,
            highlight_function=lambda _f, st=st: {"weight": st["weight"] + 1.5,
                                                  "fillOpacity": min(1.0, st["fillOpacity"] + 0.2)},
            marker=folium.CircleMarker(radius=5) if kind in ("point", "mixed") else None,
            tooltip=folium.GeoJsonTooltip(fields=tip, aliases=[f"{c}:" for c in tip], sticky=True)
            if tip else None,
            popup=folium.GeoJsonPopup(fields=pop, aliases=pop, max_width=380) if pop else None,
            control=False,
            **extra,
        ).add_to(fg)
        fg.add_to(m)

        label = escape(g["label"]) if g["label"] else escape(lcfg["name"])
        count = "" if is_ref else f"<span class='lg-n'>({_fmt_int(int(mask.sum()))})</span>"
        rows.append(f"{icon} {label} {count}")
    return rows


# ============================================================================
# 7. PUNTOS (render eficiente con canvas) + METADATOS COMPARTIDOS
# ============================================================================
class PointsScript(MacroElement):
    """Inyecta en el FeatureGroup `group` los puntos de un grupo como L.circleMarker."""

    _template = Template("""
    {% macro script(this, kwargs) %}
    (function () {
        var group = {{ this.group_name }};
        var map = {{ this.map_name }};
        var M = window[{{ this.meta_var }}];
        var D = {{ this.payload }};

        function esc(s) {
            return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }
        function cell(i, r) {                       // texto de la columna i en la fila r
            var c = M.cols[i], v = r[2 + i];
            if (c.kind === 'num') {
                return (v === null || v === undefined) ? '—'
                    : Number(v).toLocaleString('es-ES', {maximumFractionDigits: 3});
            }
            return esc(c.values[v]);
        }

        var markers = new Array(D.rows.length);
        for (var i = 0; i < D.rows.length; i++) {
            var r = D.rows[i];
            var mk = L.circleMarker([r[0], r[1]], {
                radius: D.radius, stroke: D.strokeWeight > 0,
                color: D.strokeColor, weight: D.strokeWeight, opacity: D.strokeOpacity,
                fillColor: D.color, fillOpacity: D.fillOpacity, idx: i
            });
            mk._vis = true;
            markers[i] = mk;
            mk.addTo(group);
        }
        // Registro global: lo usan los selectores para filtrar
        var F = (window[{{ this.filter_var }}] = window[{{ this.filter_var }}] || {layers: []});
        F.layers.push({group: group, markers: markers, rows: D.rows});
        // Encender/apagar una capa en el control de capas también filtra: los selectores se reajustan
        F.map = map;
        if (!F.bound) {
            F.bound = true;
            map.on('overlayadd overlayremove', function (e) {
                if (F.schedule && F.layers.some(function (l) { return l.group === e.layer; })) F.schedule();
            });
        }
        if (F.schedule) F.schedule();

        var tip = L.tooltip({direction: 'top', offset: [0, -6], opacity: 0.95});
        group.on('mouseover', function (e) {
            var r = D.rows[e.layer.options.idx], html = '';
            M.tipCols.forEach(function (i) {
                html += (html ? '<br>' : '') + '<b>' + esc(M.cols[i].name) + ':</b> ' + cell(i, r);
            });
            if (!html && D.label) html = esc(D.label);
            if (!html) return;
            tip.setLatLng(e.latlng).setContent(html);
            map.openTooltip(tip);
        });
        group.on('mouseout', function () { map.closeTooltip(tip); });

        group.on('click', function (e) {
            var r = D.rows[e.layer.options.idx], html = '';
            M.popCols.forEach(function (i) {
                html += '<tr><th>' + esc(M.cols[i].name) + '</th><td>' + cell(i, r) + '</td></tr>';
            });
            if (D.label) {
                html += '<tr><th>' + esc(D.groupLabel || 'Grupo') + '</th><td><span style="color:' +
                        D.color + ';font-weight:700;">&#9679;</span> ' + esc(D.label) + '</td></tr>';
            }
            if (!html) return;
            map.closeTooltip(tip);
            L.popup({maxWidth: 360}).setLatLng(e.latlng)
                .setContent('<table class="map-popup">' + html + '</table>').openOn(map);
        });
    })();
    {% endmacro %}
    """)

    def __init__(self, group: FeatureGroup, fmap: folium.Map, payload: dict, k: int = 0):
        super().__init__()
        self._name = "PointsScript"
        self.group_name = group.get_name()
        self.map_name = fmap.get_name()
        # cada conjunto de posiciones (k) tiene sus propios metadatos y su propio registro de filtros
        self.meta_var = json.dumps(f"PTMETA_{k}")
        self.filter_var = json.dumps(f"PTFilter_{k}")
        # "</" escapado para que el JSON nunca cierre el <script> por accidente
        self.payload = json.dumps(payload, ensure_ascii=False,
                                  separators=(",", ":")).replace("</", "<\\/")


def build_point_data(df: pd.DataFrame, pcfg: dict) -> dict:
    """
    Tablas globales de valores (una sola vez) + arrays por columna.
    Cada fila de un punto es [lat, lon, v0, v1, ...] con una posición por columna de `cols`.
    """
    slicer_cols = [c for c in pcfg.get("slicers", []) if c in df.columns]
    tip_cols = [c for c in pcfg.get("tooltip", []) if c in df.columns]
    pop_cols = [c for c in pcfg.get("popup", []) if c in df.columns]
    date_col = pcfg.get("date")
    date_on = (bool(pcfg.get("date_slicer")) and date_col in df.columns
               and pd.api.types.is_datetime64_any_dtype(df[date_col]) and df[date_col].notna().any())
    ordered = list(dict.fromkeys(tip_cols + pop_cols + slicer_cols + ([date_col] if date_on else [])))

    cols: list[dict] = []
    arrays: list[np.ndarray] = []
    slicers: list[dict] = []
    for c in ordered:
        s = df[c]
        numeric = pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)
        if c in slicer_cols or not numeric:
            codes, uniques = pd.factorize(clean_text(s), sort=True)
            cols.append({"name": c, "kind": "cat", "values": [str(u) for u in uniques]})
            arrays.append(codes.astype(np.int64))
            if c in slicer_cols:
                counts = np.bincount(codes, minlength=len(uniques))
                slicers.append({"name": c, "pos": 2 + len(cols) - 1,
                                "items": [{"name": str(u), "n": int(k)} for u, k in zip(uniques, counts)]})
        else:
            vals = pd.to_numeric(s, errors="coerce").round(3)
            arrays.append(vals.astype(object).where(vals.notna(), None).to_numpy())
            cols.append({"name": c, "kind": "num"})

    date_meta = None
    if date_on:
        s = df[date_col]
        days = ((s - EPOCH) / pd.Timedelta(days=1)).round(4)
        arrays.append(days.astype(object).where(days.notna(), None).to_numpy())
        cols.append({"name": f"{date_col} (t)", "kind": "t"})
        date_meta = {"name": date_col, "pos": 2 + len(cols) - 1,
                     "min": s.min().strftime("%Y-%m-%d"), "max": s.max().strftime("%Y-%m-%d"),
                     "minT": float(days.min()), "maxT": float(days.max())}

    meta = {"cols": cols,
            "tipCols": [ordered.index(c) for c in tip_cols],
            "popCols": [ordered.index(c) for c in pop_cols],
            "slicers": slicers, "dateSlicer": date_meta, "total": int(len(df))}
    return {"meta": meta, "arrays": arrays,
            "lat": df["__lat"].round(5).to_numpy(), "lon": df["__lon"].round(5).to_numpy()}


def add_point_layers(m: folium.Map, df: pd.DataFrame, pcfg: dict, pdata: dict, k: int = 0) -> list[str]:
    name = pcfg.get("name") or "Posiciones"
    style = pcfg.get("style", {})
    codes, groups = resolve_groups(df, style)
    radius = float(pcfg.get("radius", DEFAULT_POINT_RADIUS))
    group_label = style.get("column", "") if style.get("mode") in ("category", "numeric") else ""
    lat, lon, arrays = pdata["lat"], pdata["lon"], pdata["arrays"]
    legend_rows: list[str] = []

    for gi, g in enumerate(groups):
        idx = np.flatnonzero(codes == gi)
        if idx.size == 0:
            continue
        parts = [lat[idx].tolist(), lon[idx].tolist()] + [a[idx].tolist() for a in arrays]
        rows = [list(t) for t in zip(*parts)]
        payload = {"rows": rows, "color": g["color"], "label": g["label"], "groupLabel": group_label,
                   "radius": radius, "fillOpacity": POINT_FILL_OPACITY,
                   "strokeColor": POINT_STROKE_COLOR, "strokeWeight": POINT_STROKE_WEIGHT,
                   "strokeOpacity": POINT_STROKE_OPACITY}
        title = name if not g["label"] else f"{name} · {g['label']}"
        icon = _icon(pcfg, _swatch_circle(g["color"]))   # el mismo icono en el control de capas y en la leyenda
        fg = FeatureGroup(name=_control_name(f"{title} ({_fmt_int(int(idx.size))})", icon), show=g["show"])
        fg.add_to(m)
        fg.add_child(PointsScript(fg, m, payload, k))
        legend_rows.append(f"{icon} {escape(g['label'] or name)} "
                           f"<span class='lg-n'>({_fmt_int(int(idx.size))})</span>")
        log.info("Posiciones · %s: %d puntos.", g["label"] or name, idx.size)
    return legend_rows


# ============================================================================
# 5b. ESTILOS DE LA PÁGINA (CSS)
# ============================================================================
PAGE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<style>
  /* ---------- Tokens de diseño (un único lugar para cambiar el aspecto) ---------- */
  :root {
    --brand: __BRAND_BLUE__;
    --brand-green: __BRAND_GREEN__;
    --brand-orange: __BRAND_ORANGE__;
    --ink: #1f2d3d;
    --muted: #6b7a8a;
    --line: #e3e9ef;
    --tint: color-mix(in srgb, var(--brand) 8%, white);
    --panel-bg: rgba(255,255,255,.94);
    --radius: 12px;
    --shadow: 0 4px 16px rgba(15,35,60,.20), 0 1px 3px rgba(15,35,60,.16);
    --gap: 12px;
    --font: __UI_FONT__;
  }

  /* ---------- Tipografía y mapa base ---------- */
  .leaflet-container { font-family: var(--font); color: var(--ink); }
  .leaflet-container button, .leaflet-container input { font-family: var(--font); }
  .__BASEMAP_CLASS__ { filter: __BASEMAP_FILTER__; }

  /* ---------- Paneles propios: misma esquina, sombra y fondo ---------- */
  #info-box, .slicer, .slicer-total, #map-legend {
    background: var(--panel-bg); border-radius: var(--radius); box-shadow: var(--shadow);
    -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
    font: 12px/1.45 var(--font); color: var(--ink);
  }

  /* Tarjeta del título */
  #info-box { position: relative; flex: 0 0 auto; box-sizing: border-box;
              width: 240px; padding: 15px 14px 13px; text-align: center; overflow: hidden; }
  #info-box::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
                      background: linear-gradient(90deg, var(--brand-green) 0 33.34%,
                                  var(--brand-orange) 33.34% 66.67%, var(--brand) 66.67%); }
  #info-box img { max-width: 100%; height: auto; display: block; margin: 2px auto 8px;
                  mix-blend-mode: multiply; }   /* el fondo blanco del logo deja de verse */
  #info-box .ib-title { font-size: 13.5px; font-weight: 700; color: var(--brand); line-height: 1.3; }
  #info-box .ib-ref { color: var(--muted); font-size: 12px; }
  #info-box .ib-ref a { color: var(--brand); font-weight: 700; text-decoration: none;
                        border-bottom: 1px solid currentColor; }
  #info-box .ib-desc { margin: 5px 0 2px; color: var(--muted); font-weight: 500; font-size: 12.5px; font-weight: 600; line-height: 1.35; }
  #info-box .ib-tag { display: inline-block; padding: 2px 12px; border-radius: 999px;
                      background: var(--brand); color: #fff; font-size: 11px; font-weight: 600;
                      letter-spacing: .03em; }

  /* Barra superior izquierda: tarjeta de título + selectores tipo Power BI */
  #slicer-bar { position: fixed; top: var(--gap); left: var(--gap); z-index: 10000;
                display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--gap);
                max-width: calc(100vw - 100px); pointer-events: none; }
  #slicer-bar > * { pointer-events: auto; }
  .slicer { width: 280px; overflow: hidden; }
  .slicer-date { width: auto; }
  .slicer-date .fs-head { gap: 8px; }
  .slicer-date input[type=date] { border: 1px solid #cfd8e1; border-radius: 8px; padding: 3px 6px;
                                   font: inherit; color: var(--ink); background: #fff; }
  .slicer-date input[type=date]:focus { border-color: var(--brand); outline: none; }
  .slicer-total { display: none; padding: 7px 14px; border-radius: 999px; font-size: 11px;
                  font-weight: 600; color: var(--brand); }
  .slicer-total.on { display: block; }
  .fs-head { display: flex; align-items: center; gap: 10px; padding: 7px 10px; }
  .fs-title { font-weight: 600; color: var(--brand); white-space: nowrap; max-width: 130px;
              overflow: hidden; text-overflow: ellipsis; }
  .fs-btn { flex: 1; min-width: 0; display: flex; justify-content: space-between; align-items: center;
            gap: 6px; background: #fff; border: 1px solid #cfd8e1; border-radius: 8px;
            padding: 5px 10px; cursor: pointer; font: inherit; color: var(--ink); text-align: left; }
  .fs-btn:hover, .fs-btn:focus-visible { border-color: var(--brand); outline: none; }
  .fs-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fs-panel { display: none; border-top: 1px solid var(--line); padding: 10px; }
  .slicer.open .fs-panel { display: block; }
  .fs-search { width: 100%; box-sizing: border-box; padding: 5px 8px; margin-bottom: 6px;
               border: 1px solid #cfd8e1; border-radius: 8px; font: inherit; color: var(--ink); }
  .fs-search:focus { border-color: var(--brand); outline: none;
                     box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 18%, transparent); }
  .fs-list { max-height: 260px; overflow-y: auto; margin-top: 4px; }
  .fs-item { display: flex; align-items: center; gap: 8px; padding: 4px 4px; border-radius: 6px;
             cursor: pointer; }
  .fs-item:hover { background: var(--tint); }
  .fs-item input { accent-color: var(--brand); }
  .fs-all { border-bottom: 1px solid var(--line); border-radius: 0; font-weight: 600; }
  .fs-name { flex: 1; min-width: 0; }
  .fs-n { color: var(--muted); font-variant-numeric: tabular-nums; }
  .fs-off { opacity: .4; }
  .fs-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 8px;
             padding-top: 7px; border-top: 1px solid var(--line); color: var(--muted); }
  .fs-reset { background: none; border: none; color: var(--brand); cursor: pointer; font: inherit; }
  .slicer-date .fs-reset { font-size: 15px; padding: 0 2px; }
  .slicer:not(.slicer-date) .fs-reset { text-decoration: underline; }

  /* Leyenda */
  #map-legend { position: fixed; bottom: 40px; right: var(--gap); z-index: 9999; width: 268px;
                box-sizing: border-box; padding: 10px 14px 12px; background: rgba(255,255,255,.92);
                max-height: calc(100vh - 170px); overflow-y: auto; }
  #map-legend summary { cursor: pointer; font-weight: 700; font-size: 13px; color: var(--brand); }
  #map-legend h4 { margin: 12px 0 5px; padding-bottom: 4px; font-size: 11px; font-weight: 700;
                   letter-spacing: .07em; text-transform: uppercase; color: var(--brand);
                   border-bottom: 1px solid var(--line); }
  #map-legend .lg-row { display: flex; align-items: center; gap: 10px; margin: 5px 0; }
  .lg-sw { display: inline-block; flex: 0 0 auto; }
  .lg-circle { width: 12px; height: 12px; border-radius: 50%;
               border: 1.5px solid rgba(255,255,255,.9); box-shadow: 0 0 0 1px rgba(15,35,60,.18); }
  .lg-line { width: 26px; height: 0; }
  .lg-box { width: 22px; height: 12px; border-radius: 3px; }
  .lg-emoji { width: 22px; text-align: center; font-size: 14px; line-height: 1; }
  .lg-n { color: var(--muted); }
  /* mismos iconos dentro del control de capas (texto en línea, no flex como en la leyenda) */
  .leaflet-container .leaflet-control-layers-overlays .lg-sw { vertical-align: middle; margin-right: 4px; }

  /* ---------- Controles de Leaflet con el mismo lenguaje visual ---------- */
  .leaflet-container .leaflet-top .leaflet-control { margin-top: var(--gap); }
  .leaflet-container .leaflet-left .leaflet-control { margin-left: var(--gap); }
  .leaflet-container .leaflet-right .leaflet-control { margin-right: var(--gap); }
  .leaflet-container .leaflet-bottom .leaflet-control { margin-bottom: 10px; }

  .leaflet-container .leaflet-bar,
  .leaflet-container .leaflet-control-layers {
    border: none !important; border-radius: var(--radius); box-shadow: var(--shadow) !important;
    background: var(--panel-bg); overflow: hidden;
  }
  .leaflet-container .leaflet-bar a {
    width: 34px; height: 34px; line-height: 34px; background: transparent; color: var(--ink);
    border-radius: 0 !important; border-bottom: 1px solid var(--line); font-family: var(--font);
  }
  .leaflet-container .leaflet-bar a:last-child { border-bottom: none; }
  .leaflet-container .leaflet-bar a:hover { background: var(--tint); color: var(--brand); }
  .leaflet-container .leaflet-control-layers-toggle {
    width: 34px; height: 34px; background-size: 20px 20px; background-position: center;
    background-repeat: no-repeat;
  }
  .leaflet-container .leaflet-control-layers-expanded { padding: 10px 14px; font-size: 12px; color: var(--ink); }
  .leaflet-container .leaflet-control-layers-selector { accent-color: var(--brand); }
  .leaflet-container .leaflet-control-layers-separator { border-top: 1px solid var(--line); }
  .map-tools a { font-size: 17px; cursor: pointer; }
  .map-tools a.active { background: var(--brand) !important; color: #fff !important; }
  .tl-box { display: inline-block; width: 13px; height: 9px; border: 2px dashed currentColor; vertical-align: middle; }
  .zb-rect { position: absolute; z-index: 700; pointer-events: none;
             border: 1.5px dashed var(--brand-orange);
             background: color-mix(in srgb, var(--brand-orange) 15%, transparent); }

  /* Esquina inferior izquierda: coordenadas, minimapa y escala, alineados y con aire */
  .leaflet-container .leaflet-control-mouseposition {
    background: var(--panel-bg); color: var(--ink); border-radius: 999px; padding: 3px 12px;
    box-shadow: var(--shadow); letter-spacing: .01em;
    font: 500 11px/1.5 ui-monospace, "SF Mono", Consolas, "Courier New", monospace;
  }
  .leaflet-container .leaflet-control-minimap {
    border: 2px solid rgba(255,255,255,.95); border-radius: var(--radius);
    box-shadow: var(--shadow); background: #fff; overflow: hidden;
  }
  .leaflet-container .leaflet-control-scale-line {
    background: var(--panel-bg); color: var(--ink); border: 2px solid #52667a; border-top: none;
    font-size: 10.5px; line-height: 1.3; padding: 1px 8px 1px 6px; text-shadow: none;
  }
  .leaflet-container .leaflet-control-scale-line:not(:first-child) {
    border-top: 2px solid #52667a; border-bottom: none; margin-top: -2px;
  }

  /* Atribución discreta */
  .leaflet-container .leaflet-control-attribution {
    margin: 0 !important; padding: 1px 8px; font-size: 10px; color: var(--muted);
    background: rgba(255,255,255,.62); border-radius: 8px 0 0 0;
  }
  .leaflet-container .leaflet-control-attribution a { color: var(--muted); }

  /* ---------- Popups y tooltips ---------- */
  .leaflet-container .leaflet-popup-content-wrapper { border-radius: var(--radius); box-shadow: var(--shadow); }
  .leaflet-container .leaflet-popup-content { margin: 10px 12px; font: 12px/1.45 var(--font); }
  .leaflet-container .leaflet-popup-tip { box-shadow: var(--shadow); }
  .leaflet-container a.leaflet-popup-close-button { color: var(--muted); }
  .leaflet-tooltip { font: 12px/1.45 var(--font); color: var(--ink); padding: 6px 10px;
                     border-radius: 8px; box-shadow: var(--shadow); }
  .map-popup { border-collapse: collapse; font: 12px/1.4 var(--font); min-width: 250px; }
  .map-popup th { text-align: left; background: var(--tint); color: var(--brand); font-weight: 600;
                  padding: 5px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  .map-popup td { padding: 5px 8px; border-bottom: 1px solid var(--line); }
  .map-popup tr:last-child th, .map-popup tr:last-child td { border-bottom: none; }
</style>
"""


def _render_page_css() -> str:
    """Sustituye los marcadores __X__ del CSS por los valores configurados arriba."""
    tokens = {"__BRAND_BLUE__": BRAND_BLUE, "__BRAND_GREEN__": BRAND_GREEN,
              "__BRAND_ORANGE__": BRAND_ORANGE, "__UI_FONT__": UI_FONT,
              "__BASEMAP_FILTER__": BASEMAP_FILTER, "__BASEMAP_CLASS__": BASEMAP_CLASS}
    css = PAGE_CSS
    for key, value in tokens.items():
        css = css.replace(key, value)
    return css


# ============================================================================
# 5c. CONTROLES DEL MAPA
# ============================================================================
class MapToolsControl(MacroElement):
    """Zoom +/-, 'vista inicial' y 'zoom a un área' (arrastrar un rectángulo), arriba a la derecha."""

    _template = Template("""
    {% macro script(this, kwargs) %}
    (function () {
        var map = {{ this._parent.get_name() }};
        var home = {{ this.bounds }};
        var btnBox, el = null, p0 = null, active = false, swallow = false;

        L.control.zoom({position: 'topright', zoomInTitle: 'Acercar', zoomOutTitle: 'Alejar'}).addTo(map);

        function setActive(on) {
            active = on;
            L.DomUtil[on ? 'addClass' : 'removeClass'](btnBox, 'active');
            map.getContainer().style.cursor = on ? 'crosshair' : '';
            if (on) map.dragging.disable(); else map.dragging.enable();
            if (!on && el) { L.DomUtil.remove(el); el = null; }
        }

        var Tools = L.Control.extend({
            options: {position: 'topright'},
            onAdd: function () {
                var bar = L.DomUtil.create('div', 'leaflet-bar map-tools');
                var a = L.DomUtil.create('a', '', bar);
                a.href = '#'; a.title = 'Vista inicial'; a.innerHTML = '&#8962;';
                btnBox = L.DomUtil.create('a', '', bar);
                btnBox.href = '#'; btnBox.title = 'Zoom a un área (arrastra un rectángulo)';
                btnBox.innerHTML = '<span class="tl-box"></span>';
                L.DomEvent.disableClickPropagation(bar);
                L.DomEvent.on(a, 'click', function (e) {
                    L.DomEvent.preventDefault(e);
                    map.fitBounds(home, {padding: {{ this.padding }}});
                });
                L.DomEvent.on(btnBox, 'click', function (e) {
                    L.DomEvent.preventDefault(e);
                    setActive(!active);
                });
                return bar;
            }
        });
        map.addControl(new Tools());

        // Rectángulo dibujado con un <div> (no con una capa Leaflet, para no repintar el canvas de los puntos)
        map.on('mousedown', function (e) {
            if (!active || (e.originalEvent && e.originalEvent.button !== 0)) return;
            p0 = e.containerPoint;
            el = L.DomUtil.create('div', 'zb-rect', map.getContainer());
        });
        map.on('mousemove', function (e) {
            if (!el) return;
            var p = e.containerPoint;
            el.style.left = Math.min(p0.x, p.x) + 'px';  el.style.top = Math.min(p0.y, p.y) + 'px';
            el.style.width = Math.abs(p.x - p0.x) + 'px'; el.style.height = Math.abs(p.y - p0.y) + 'px';
        });
        map.on('mouseup', function (e) {
            if (!el) return;
            var p = e.containerPoint;
            L.DomUtil.remove(el); el = null;
            if (Math.abs(p.x - p0.x) > 8 && Math.abs(p.y - p0.y) > 8) {
                swallow = true; setTimeout(function () { swallow = false; }, 100);   // evita abrir un popup al soltar
                map.fitBounds(L.latLngBounds(map.containerPointToLatLng(p0), map.containerPointToLatLng(p)));
                setActive(false);
            }
        });
        map.getContainer().addEventListener('click', function (e) {
            if (swallow) { e.stopPropagation(); e.preventDefault(); swallow = false; }
        }, true);
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && active) setActive(false); });
    })();
    {% endmacro %}
    """)

    def __init__(self, bounds: list[list[float]]):
        super().__init__()
        self._name = "MapToolsControl"
        self.bounds = json.dumps(bounds)
        self.padding = json.dumps(list(FIT_PADDING))


def add_map_plugins(m: folium.Map, bounds: list[list[float]]) -> None:
    """Zoom, vista inicial, zoom a un área, coordenadas y minimapa."""
    # Arriba a la derecha, bajo el control de capas (el orden de las llamadas es el orden en pantalla)
    m.add_child(MapToolsControl(bounds))
    # Abajo a la izquierda, sobre la escala: primero las coordenadas, encima el minimapa
    MousePosition(position="bottomleft", separator=" | ", num_digits=4,
                  prefix="Lat | Lon:").add_to(m)
    mini_tiles = folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri", control=False, className=BASEMAP_CLASS)
    MiniMap(tile_layer=mini_tiles, position="bottomleft", width=170, height=170,
            toggle_display=True, zoom_level_offset=-5,
            aimingRectOptions={"color": BRAND_ORANGE, "weight": 1.6, "interactive": False}
            ).add_to(m)


def safe_html_path(output_path: Path) -> Path:
    """La salida siempre es un .html: si la ruta apunta a otro tipo de archivo (p. ej. un dataset
    elegido por error) se le añade .html en lugar de sobrescribirlo."""
    p = Path(output_path).expanduser().resolve()
    if p.suffix.lower() not in (".html", ".htm"):
        fixed = p.with_name(p.name + ".html")
        log.warning("La salida «%s» no es un .html; se guardará como «%s».", p.name, fixed.name)
        p = fixed
    return p


def save_map(m: folium.Map, output_path: Path) -> Path:
    output_path = safe_html_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output_path))
    log.info("Mapa guardado: %s (%.1f MB)", output_path, output_path.stat().st_size / 1e6)
    return output_path


# ============================================================================
# 8. APERTURA EN CHROME
# ============================================================================
def _find_chrome() -> Optional[str]:
    """Localiza el ejecutable de Google Chrome en Windows, macOS o Linux."""
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    for c in candidates:
        if c.is_file():
            return str(c)
    for exe in ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def open_in_chrome(html_path: Path) -> None:
    """Abre el HTML en una ventana nueva de Chrome; si no lo encuentra, usa el navegador por defecto."""
    url = Path(html_path).resolve().as_uri()
    chrome = _find_chrome()
    try:
        if chrome:
            # "%s" se sustituye por la URL; --new-window fuerza ventana nueva
            browser = webbrowser.BackgroundBrowser([chrome, "--new-window", "%s"])
            webbrowser.register("chrome-mapa-vms", None, browser)
            if webbrowser.get("chrome-mapa-vms").open(url):
                log.info("Abierto en Google Chrome.")
                return
        log.warning("Chrome no encontrado; se usa el navegador predeterminado.")
        webbrowser.open(url, new=1)
    except Exception as exc:  # noqa: BLE001
        log.error("No se pudo abrir el navegador (%s). Abre manualmente: %s", exc, html_path)


# ============================================================================
# 8. BARRA SUPERIOR: título opcional + selectores tipo Power BI
# ============================================================================
SLICER_JS = r"""
<script>
(function () {
  var M = window.PTMETA___K__;
  if (!M) return;
  var F = (window.PTFilter___K__ = window.PTFilter___K__ || {layers: []});
  // con varios conjuntos de posiciones, cada filtro lleva el nombre de su conjunto
  function ttl(n) { return (M.label ? M.label + ' \u00b7 ' : '') + n; }
  var bar = document.getElementById('slicer-bar');
  var totalEl = document.getElementById('slicer-total-__K__');
  var S = F.slicers = [];
  var DT = F.date = null;
  var timer = null;
  var fmt = function (n) { return n.toLocaleString('es-ES'); };

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Recalcula TODO en una sola pasada por los puntos:
  //  · qué puntos se ven: AND de todos los selectores y del rango de fechas, solo en las capas encendidas;
  //  · cuántos puntos hay en cada opción de cada selector con el RESTO de filtros aplicados (el suyo no),
  //    de modo que los selectores se influyen entre sí y una opción sin puntos queda «no disponible»;
  //  · el mensaje «X de Y posiciones visibles».
  function applyFilter() {
    var act = [];
    S.forEach(function (s, i) { if (s.selected.size !== s.items.length) act.push(i); });
    var dtOn = !!(DT && DT.on), shown = 0, hiddenLayers = false, map = F.map;
    var avail = S.map(function (s) { return new Int32Array(s.items.length); });
    F.layers.forEach(function (ly) {
      var on = !map || map.hasLayer(ly.group);        // ¿está encendida en el control de capas?
      if (!on) hiddenLayers = true;
      var rows = ly.rows, ms = ly.markers;
      for (var i = 0; i < ms.length; i++) {
        var r = rows[i], fails = 0, failA = -1, dFail = false;
        for (var k = 0; k < act.length; k++) {
          var a = S[act[k]];
          if (!a.selected.has(r[a.pos])) { fails++; failA = act[k]; if (fails > 1) break; }
        }
        if (fails < 2 && dtOn) {
          var t = r[DT.pos];
          dFail = !(t !== null && t >= DT.from && t < DT.to);
          if (dFail) fails++;
        }
        var want = fails === 0;
        if (on) {
          if (want) {                                  // pasa todo: cuenta para todas las opciones
            shown++;
            for (var j = 0; j < S.length; j++) avail[j][r[S[j].pos]]++;
          } else if (fails === 1 && !dFail) {          // solo lo frena UN selector: cuenta para ese
            avail[failA][r[S[failA].pos]]++;
          }
        }
        var mk = ms[i];
        if (want && !mk._vis) { ly.group.addLayer(mk); mk._vis = true; }
        else if (!want && mk._vis) { ly.group.removeLayer(mk); mk._vis = false; }
      }
    });
    S.forEach(function (s, j) { s.avail = avail[j]; if (s.render) s.render(shown); });
    if (totalEl) {
      totalEl.classList.toggle('on', act.length > 0 || dtOn || hiddenLayers);
      totalEl.textContent = (M.label ? M.label + ': ' : '') + fmt(shown) + ' de ' + fmt(M.total) + ' posiciones visibles';
    }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(applyFilter, 150); }
  F.schedule = schedule;

  function buildSlicer(sd) {
    var st = {pos: sd.pos, items: sd.items,
              selected: new Set(sd.items.map(function (_, i) { return i; }))};
    S.push(st);
    var root = document.createElement('div');
    root.className = 'slicer';
    root.innerHTML =
      '<div class="fs-head"><span class="fs-title" title="' + esc(ttl(sd.name)) + '">' + esc(ttl(sd.name)) + '</span>' +
      '<button class="fs-btn" type="button"><span class="fs-label">Todos</span><span>&#9662;</span></button></div>' +
      '<div class="fs-panel"><input class="fs-search" type="text" placeholder="Buscar…" autocomplete="off">' +
      '<label class="fs-item fs-all"><input type="checkbox" class="fs-allbox" checked>' +
      '<span class="fs-name">Seleccionar todo</span></label><div class="fs-list"></div>' +
      '<div class="fs-foot"><span class="fs-count"></span>' +
      '<button class="fs-reset" type="button">Restablecer</button></div></div>';
    bar.appendChild(root);
    var q = function (c) { return root.querySelector(c); };
    var list = q('.fs-list'), allBox = q('.fs-allbox'), label = q('.fs-label'), count = q('.fs-count');
    var items = [];

    st.items.forEach(function (it, i) {
      var lb = document.createElement('label');
      lb.className = 'fs-item';
      lb.innerHTML = '<input type="checkbox" checked><span class="fs-name">' + esc(it.name) +
                     '</span><span class="fs-n">' + fmt(it.n) + '</span>';
      lb._i = i; lb._name = it.name.toLowerCase(); lb._box = lb.firstChild; lb._n = lb.lastChild;
      list.appendChild(lb); items.push(lb);
    });
    function visibleItems() { return items.filter(function (lb) { return lb.style.display !== 'none'; }); }

    function refresh() {
      var n = st.selected.size, total = st.items.length, sum = 0;
      st.selected.forEach(function (i) { sum += st.items[i].n; });
      label.textContent = n === total ? 'Todos' : n === 0 ? 'Ninguno'
          : n === 1 ? st.items[st.selected.values().next().value].name : n + ' seleccionados';
      if (!st.avail) count.textContent = fmt(sum) + ' de ' + fmt(M.total) + ' posiciones';
      var vis = visibleItems();
      var k = vis.filter(function (lb) { return st.selected.has(lb._i); }).length;
      allBox.checked = vis.length > 0 && k === vis.length;
      allBox.indeterminate = k > 0 && k < vis.length;
    }
    // Tras cada recálculo: nº de posiciones de cada opción con el resto de filtros, y cuáles no están disponibles
    st.render = function (shown) {
      items.forEach(function (lb) {
        var n = st.avail[lb._i];
        lb._n.textContent = fmt(n);
        lb.classList.toggle('fs-off', n === 0);
        lb.title = n === 0 ? 'No disponible con los filtros actuales' : '';
      });
      count.textContent = fmt(shown) + ' de ' + fmt(M.total) + ' posiciones';
    };
    function changed() { refresh(); schedule(); }

    list.addEventListener('change', function (e) {
      var lb = e.target.parentNode;
      if (e.target.checked) st.selected.add(lb._i); else st.selected.delete(lb._i);
      changed();
    });
    allBox.addEventListener('change', function () {      // actúa sobre los visibles (tras buscar)
      visibleItems().forEach(function (lb) {
        lb._box.checked = allBox.checked;
        if (allBox.checked) st.selected.add(lb._i); else st.selected.delete(lb._i);
      });
      changed();
    });
    q('.fs-search').addEventListener('input', function () {
      var t = this.value.trim().toLowerCase();
      items.forEach(function (lb) { lb.style.display = lb._name.indexOf(t) === -1 ? 'none' : ''; });
      refresh();
    });
    q('.fs-reset').addEventListener('click', function () {
      items.forEach(function (lb) { lb._box.checked = true; st.selected.add(lb._i); });
      changed();
    });
    q('.fs-btn').addEventListener('click', function () { root.classList.toggle('open'); });
    refresh();
  }

  function buildDate(dd) {
    DT = F.date = {pos: dd.pos, from: dd.minT, to: dd.maxT + 1, on: false};
    var root = document.createElement('div');
    root.className = 'slicer slicer-date';
    root.innerHTML =
      '<div class="fs-head"><span class="fs-title" title="' + esc(ttl(dd.name)) + '">' + esc(ttl(dd.name)) + '</span>' +
      '<input type="date" class="dt-from" min="' + dd.min + '" max="' + dd.max + '" value="' + dd.min + '">' +
      '<span>&ndash;</span>' +
      '<input type="date" class="dt-to" min="' + dd.min + '" max="' + dd.max + '" value="' + dd.max + '">' +
      '<button class="fs-reset" type="button" title="Restablecer">&#8634;</button></div>';
    bar.appendChild(root);
    var from = root.querySelector('.dt-from'), to = root.querySelector('.dt-to');
    function day(v, fallback) { return v ? Date.parse(v + 'T00:00:00Z') / 86400000 : fallback; }
    function update() {
      var a = day(from.value, dd.minT), b = day(to.value, dd.maxT);
      DT.from = a; DT.to = b + 1;
      DT.on = !(a <= dd.minT && b + 1 > dd.maxT);
      schedule();
    }
    from.addEventListener('change', update);
    to.addEventListener('change', update);
    root.querySelector('.fs-reset').addEventListener('click', function () {
      from.value = dd.min; to.value = dd.max; update();
    });
  }

  if (bar) {
    M.slicers.forEach(buildSlicer);
    if (M.dateSlicer) buildDate(M.dateSlicer);
    if (totalEl) bar.appendChild(totalEl);
  }
  document.addEventListener('click', function (e) {     // cierra los desplegables al hacer clic fuera
    var open = document.querySelectorAll('.slicer.open');
    for (var i = 0; i < open.length; i++) { if (!open[i].contains(e.target)) open[i].classList.remove('open'); }
  });
})();
</script>
"""


def _logo_src(logo: str) -> str:
    """URL tal cual; archivo local -> data URI (el HTML sigue siendo autocontenido)."""
    if re.match(r"^https?://", logo, re.I):
        return logo
    p = Path(logo).expanduser()
    if not p.is_file():
        log.warning("Logo no encontrado (%s); se omite.", logo)
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def add_top_bar(m: folium.Map, cfg: dict, pdatas: list[dict]) -> None:
    """Metadatos de los puntos (uno por conjunto de posiciones) + barra con título y selectores."""
    root = m.get_root()
    metas = [pd_["meta"] for pd_ in pdatas]
    with_slicers = list(range(len(metas)))    # todos: el control de capas también filtra y debe poder avisarlo
    title, subtitle = cfg.get("title", ""), cfg.get("subtitle", "")

    html = ""
    if title or with_slicers:
        html += '<div id="slicer-bar">'
        if title:
            logo = _logo_src(cfg["logo"]) if cfg.get("logo") else ""
            img = (f'<img src="{escape(logo, quote=True)}" alt="Logo" '
                   f'style="width:{int(cfg.get("logo_width", 140))}px;" onerror="this.style.display=\'none\'">'
                   if logo else "")
            sub = f'<div class="ib-desc">{escape(subtitle)}</div>' if subtitle else ""
            html += (f'<div id="info-box">{img}<div class="ib-title">{escape(title)}</div>{sub}</div>')
        for k in with_slicers:
            html += f'<div class="slicer-total" id="slicer-total-{k}"></div>'
        html += "</div>"
    for k, meta in enumerate(metas):
        meta_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        html += f"<script>window.PTMETA_{k} = {meta_json};</script>"
        if k in with_slicers:
            html += SLICER_JS.replace("__K__", str(k))
    if html:
        root.html.add_child(Element(html))


# ============================================================================
# 9. CONSTRUCCIÓN DEL MAPA A PARTIR DE LA CONFIGURACIÓN
# ============================================================================
def validate_config(cfg: dict) -> None:
    if not isinstance(cfg, dict) or "layers" not in cfg:
        raise ConfigError("El archivo de configuración no tiene el formato esperado.")
    if not cfg.get("positions") and not cfg["layers"]:
        raise ConfigError("La configuración no contiene ni posiciones ni capas.")
    if cfg.get("version", 1) > CONFIG_VERSION:
        log.warning("La configuración es de una versión más nueva del asistente.")


def position_configs(cfg: dict) -> list[dict]:
    """`positions` puede ser un solo conjunto (dict, formato antiguo) o una lista de conjuntos."""
    pos = cfg.get("positions")
    if not pos:
        return []
    return [pos] if isinstance(pos, dict) else list(pos)


def build_map(cfg: dict, cache: Optional[dict] = None) -> Path:
    """
    Genera el HTML. `cache` evita releer los datos que ya estaban cargados:
      cache["positions_raws"] = {k: DataFrame}   (k = posición en cfg["positions"])
      cache["layers"]         = {i: GeoDataFrame}
    Al terminar deja en cache["stats"] las filas leídas/descartadas/dibujadas de cada conjunto.
    """
    validate_config(cfg)
    cache = cache if cache is not None else {}
    cache["stats"] = []
    seen: set[str] = set()

    def unique_name(base: str) -> str:
        name, k = base, 2
        while name in seen:
            name, k = f"{base} ({k})", k + 1
        seen.add(name)
        return name

    datasets: list[tuple[dict, pd.DataFrame]] = []
    raws = cache.get("positions_raws", {})
    for k, pc in enumerate(position_configs(cfg)):
        raw = raws.get(k)
        if raw is None and k == 0:
            raw = cache.get("positions_raw")          # compatibilidad con el asistente de consola
        df_k = prepare_positions(pc, raw)
        pc = dict(pc)
        pc["name"] = unique_name(pc.get("name") or f"Posiciones {k + 1}")
        datasets.append((pc, df_k))
        cache["stats"].append({"name": pc["name"], **df_k.attrs})

    layers: list[tuple[dict, gpd.GeoDataFrame]] = []
    for i, lcfg in enumerate(cfg["layers"]):
        try:
            gdf = cache.get("layers", {}).get(i)
            gdf = gdf if gdf is not None else load_vector(lcfg)
        except ConfigError:
            raise
        except Exception as exc:  # noqa: BLE001 - se omite la capa y se sigue
            log.error("[%s] no se pudo cargar (%s). La capa se omite.", lcfg.get("name"), exc)
            continue
        lcfg = dict(lcfg)
        lcfg["name"] = unique_name(lcfg.get("name") or f"Capa {i + 1}")
        layers.append((lcfg, gdf))
        log.info("[%s] cargada: %d entidades.", lcfg["name"], len(gdf))

    if datasets:
        bounds = [[min(float(d["__lat"].min()) for _, d in datasets), min(float(d["__lon"].min()) for _, d in datasets)],
                  [max(float(d["__lat"].max()) for _, d in datasets), max(float(d["__lon"].max()) for _, d in datasets)]]
    elif layers:
        allb = np.array([g.total_bounds for _, g in layers])
        bounds = [[float(allb[:, 1].min()), float(allb[:, 0].min())],
                  [float(allb[:, 3].max()), float(allb[:, 2].max())]]
    else:
        raise ConfigError("No hay nada que representar: ninguna capa se pudo cargar.")

    m = create_base_map(bounds)

    if any(l.get("on_top") for l, _ in layers):
        # pane propio (con su propio canvas) por encima de los puntos, que van en overlayPane (400)
        CustomPane(TOP_PANE, z_index=450, pointer_events=True).add_to(m)

    layer_sections: dict[str, list[str]] = {}
    ref_rows: list[str] = []
    for lcfg, gdf in layers:                       # lo último que se añade queda encima
        rows = add_vector_layer(m, gdf, lcfg)
        if lcfg.get("reference"):
            ref_rows.extend(rows)
        else:
            layer_sections[lcfg["name"]] = rows
    if ref_rows:
        layer_sections[REFERENCE_SECTION] = ref_rows   # un único subtítulo, al final de la leyenda

    sections: dict[str, list[str]] = {}
    pdatas: list[dict] = []
    for k, (pc, df_k) in enumerate(datasets):
        pdata = build_point_data(df_k, pc)
        if len(datasets) > 1:
            pdata["meta"]["label"] = pc["name"]    # los filtros indicarán a qué conjunto pertenecen
        pdatas.append(pdata)
        sections[pc["name"]] = add_point_layers(m, df_k, pc, pdata, k)
    sections.update(layer_sections)

    add_legend(m, sections)
    add_top_bar(m, cfg, pdatas)
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    add_map_plugins(m, bounds)
    return save_map(m, Path(cfg.get("output") or "mapa_interactivo.html"))


# ============================================================================
# 10. ASISTENTE INTERACTIVO (explorador de archivos + preguntas por consola)
# ============================================================================
_NO_DIALOGS = False


def step(title: str) -> None:
    print("\n" + "─" * 70 + f"\n  {title}\n" + "─" * 70)


def ask_text(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    ans = input(f"  {prompt}{suffix}: ").strip()
    return ans if ans else (default or "")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "S/n" if default else "s/N"
    while True:
        ans = input(f"  {prompt} ({hint}): ").strip().lower()
        if not ans:
            return default
        if ans in ("s", "si", "sí", "y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("   · Responde 's' o 'n'.")


def ask_number(prompt: str, default: float, lo: float, hi: float, integer: bool = False) -> float:
    while True:
        ans = input(f"  {prompt} [{default:g}]: ").strip().replace(",", ".")
        if not ans:
            return int(default) if integer else default
        try:
            v = float(ans)
            if lo <= v <= hi:
                return int(v) if integer else v
        except ValueError:
            pass
        print(f"   · Introduce un número entre {lo:g} y {hi:g}.")


def ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    """Menú numerado. Devuelve el índice (0-based)."""
    if prompt:
        print(f"\n  {prompt}")
    for i, o in enumerate(options, 1):
        print(f"    {i}) {o}")
    while True:
        ans = input(f"  Opción [{default}]: ").strip()
        if not ans:
            return default - 1
        if ans.isdigit() and 1 <= int(ans) <= len(options):
            return int(ans) - 1
        print(f"   · Elige un número entre 1 y {len(options)}.")


def ask_color(prompt: str, default: str) -> str:
    while True:
        ans = input(f"  {prompt} [{default}]: ").strip()
        if not ans:
            return default
        c = normalize_color(ans)
        if c:
            return c
        print("   · Color no válido. Usa #RRGGBB o un nombre (rojo, azul, verde, naranja, morado…).")


def _parse_indices(text: str, n: int) -> list[int]:
    out: list[int] = []
    for tok in re.split(r"[,\s;]+", text.strip()):
        if not tok:
            continue
        if re.fullmatch(r"\d+-\d+", tok):
            a, b = (int(x) for x in tok.split("-"))
            rng = range(min(a, b), max(a, b) + 1)
        elif tok.isdigit():
            rng = [int(tok)]
        else:
            raise ValueError(tok)
        for k in rng:
            if not 1 <= k <= n:
                raise ValueError(tok)
            if k - 1 not in out:
                out.append(k - 1)
    return out


def ask_column(prompt: str, cols: list[str], default: Optional[str] = None,
               allow_none: bool = False) -> Optional[str]:
    dflt = (cols.index(default) + 1) if default in cols else None
    hint = f" [{dflt}]" if dflt else (" (Enter = ninguna)" if allow_none else "")
    while True:
        ans = input(f"  {prompt}{hint}: ").strip()
        if not ans:
            if dflt:
                return cols[dflt - 1]
            if allow_none:
                return None
        elif ans.isdigit() and 1 <= int(ans) <= len(cols):
            return cols[int(ans) - 1]
        elif ans in cols:
            return ans
        print(f"   · Escribe el número de la columna (1-{len(cols)}).")


def ask_columns(prompt: str, cols: list[str], default: Optional[list[str]] = None) -> list[str]:
    """Multi-selección: '1,3,5-7', 'todas', 'ninguna' o Enter (= valor por defecto)."""
    default = default or []
    shown = ", ".join(default[:4]) + ("…" if len(default) > 4 else "") if default else "ninguna"
    while True:
        ans = input(f"  {prompt}\n    (números separados por comas, 'todas', 'ninguna'; Enter = {shown}): ").strip()
        low = ans.lower()
        if not ans:
            return list(default)
        if low in ("todas", "todos", "*"):
            return list(cols)
        if low in ("ninguna", "ninguno", "0", "-"):
            return []
        try:
            return [cols[i] for i in _parse_indices(ans, len(cols))]
        except ValueError:
            print(f"   · Entrada no válida. Usa números de 1 a {len(cols)}.")


def print_columns(df: pd.DataFrame) -> list[str]:
    cols = visible_columns(df)
    print()
    for i, c in enumerate(cols, 1):
        nun = _fmt_int(int(df[c].nunique(dropna=True)))
        print(f"    {i:>3}) {str(c)[:40]:<40} {column_kind(df[c]):<7} {nun:>9} valores distintos")
    print()
    return cols


def pick_file(title: str, filetypes: list[tuple[str, str]], initialdir: Optional[str] = None) -> Optional[Path]:
    """Explorador de archivos nativo (tkinter); si no está disponible, pide la ruta escrita."""
    print(f"\n  {title}")
    if not _NO_DIALOGS:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                chosen = filedialog.askopenfilename(title=title, filetypes=filetypes, initialdir=initialdir)
            finally:
                root.destroy()
            if chosen:
                print(f"    → {chosen}")
            return Path(chosen) if chosen else None
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo abrir el explorador de archivos (%s). Escribe la ruta.", exc)
    raw = input("    Ruta del archivo (Enter = omitir): ").strip().strip('"').strip("'")
    return Path(raw).expanduser() if raw else None


def pick_save(title: str, initialdir: str, initialfile: str) -> Path:
    if not _NO_DIALOGS:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                chosen = filedialog.asksaveasfilename(
                    title=title, initialdir=initialdir, initialfile=initialfile,
                    defaultextension=".html", filetypes=[("Mapa HTML", "*.html")])
            finally:
                root.destroy()
            return Path(chosen) if chosen else Path(initialdir) / initialfile
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo abrir el explorador de archivos (%s).", exc)
    raw = ask_text("Ruta del HTML de salida", str(Path(initialdir) / initialfile))
    return Path(raw.strip('"').strip("'")).expanduser()


def _file_types(exts: set[str], label: str) -> list[tuple[str, str]]:
    pattern = " ".join(f"*{e}" for e in sorted(exts))
    return [(label, pattern), ("Todos los archivos", "*.*")]


# ---- estilo (color) ---------------------------------------------------------
def ask_style(df: pd.DataFrame, what: str, default_color: str) -> dict:
    """Pregunta cómo colorear: un color, por categorías o por rangos numéricos."""
    cols = visible_columns(df)
    mode = ask_choice(f"¿Cómo quieres colorear {what}?",
                      ["Un solo color",
                       "Por categorías de una columna (una capa por categoría)",
                       "Por rangos de una columna numérica"], default=1)

    if mode == 0:
        return {"mode": "single", "color": ask_color("Color (nombre o #RRGGBB)", default_color)}

    if mode == 1:
        print_columns(df)
        col = ask_column("Columna por la que categorizar", cols)
        txt = clean_text(df[col])
        counts = txt.value_counts()
        if len(counts) > MAX_CATEGORIES_WARNING:
            print(f"   · «{col}» tiene {len(counts)} categorías: se crearán {len(counts)} capas.")
            if not ask_yes_no("¿Continuar?", False):
                return ask_style(df, what, default_color)
        cats = [str(c) for c in counts.index]
        colors = assign_colors(cats)
        while True:
            print("\n    Colores asignados:")
            for i, c in enumerate(cats[:25], 1):
                print(f"      {i:>2}) {c[:36]:<36} {colors[c]}  ({_fmt_int(int(counts[c]))})")
            if len(cats) > 25:
                print(f"      … y {len(cats) - 25} categorías más (se les asignan colores automáticamente)")
            if not ask_yes_no("¿Quieres cambiar algún color?", False):
                break
            k = ask_column("Número de la categoría a recolorear", cats[:25])
            colors[k] = ask_color(f"Nuevo color para «{k}»", colors[k])
        hidden: list[str] = []
        if len(cats) > 1:
            hidden = ask_columns("¿Alguna categoría debe aparecer DESACTIVADA al abrir el mapa?",
                                 cats[:25], default=[])
        return {"mode": "category", "column": col, "colors": colors, "hidden": hidden}

    num_cols = [c for c in cols if column_kind(df[c]) == "número"]
    if not num_cols:
        print("   · No hay columnas numéricas; se usa un solo color.")
        return {"mode": "single", "color": ask_color("Color (nombre o #RRGGBB)", default_color)}
    print()
    for i, c in enumerate(num_cols, 1):
        print(f"    {i:>3}) {c}")
    col = ask_column("Columna numérica", num_cols)
    classes = int(ask_number("Número de rangos (cuantiles)", 5, 2, 9, integer=True))
    pal = list(RAMPS)
    p = ask_choice("Paleta de colores", ["Amarillo → rojo", "Azules", "Viridis (verde-azul-amarillo)",
                                         "Azul → rojo (divergente)"], default=1)
    return {"mode": "numeric", "column": col, "classes": classes, "palette": pal[p]}


def _describe_style(style: dict) -> str:
    mode = style.get("mode")
    if mode == "category":
        return f"por categorías de «{style['column']}»"
    if mode == "numeric":
        return f"por rangos de «{style['column']}» ({style['classes']} clases)"
    return f"un solo color ({style.get('color')})"


# ---- posiciones ---------------------------------------------------------------
def wizard_positions(path: Path, cache: dict) -> dict:
    sheet: Optional[str] = None
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        sheets = list_sheets(path)
        sheet = sheets[0] if len(sheets) == 1 else sheets[ask_choice("Hojas del Excel:", sheets, 1)]
    log.info("Leyendo «%s» (puede tardar un poco)…", path.name)
    raw = read_table(path, sheet)
    cache["positions_raw"] = raw
    print(f"\n  {_fmt_int(len(raw))} filas · {len(raw.columns)} columnas")
    cols = print_columns(raw)

    lat = ask_column("Columna de LATITUD", cols, guess_lat(raw))
    lon = ask_column("Columna de LONGITUD", cols, guess_lon(raw))
    date = ask_column("Columna de FECHA", cols, guess_date(raw), allow_none=True)

    pcfg: dict[str, Any] = {"path": str(path), "sheet": sheet, "lat": lat, "lon": lon, "date": date}
    df = prepare_positions(pcfg, raw)
    print(f"  → {_fmt_int(len(df))} posiciones válidas.")
    if len(df) > MAX_POINTS_WARNING:
        print("   · Con tantos puntos el HTML será pesado y puede ir lento.")
        mx = ask_number("Submuestrear a cuántos puntos (0 = todos)", 0, 0, len(df), integer=True)
        pcfg["max_points"] = int(mx) or None

    pcfg["name"] = ask_text("Nombre de la capa de posiciones", path.stem)
    pcfg["style"] = ask_style(df, "los puntos", "#0b4a9e")
    pcfg["radius"] = ask_number("Tamaño (radio) de los puntos en px", DEFAULT_POINT_RADIUS, 0.5, 15)

    print("\n  Columnas disponibles:")
    cols = print_columns(df)
    others = [c for c in cols if c not in (lat, lon)]
    pcfg["tooltip"] = ask_columns("Campos del TOOLTIP (al pasar el ratón por un punto)",
                                  cols, default=others[:3])
    pcfg["popup"] = ask_columns("Campos del POPUP (al hacer clic en un punto)",
                                cols, default=others[:30])
    slicers = ask_columns("Selectores tipo Power BI (lista desplegable con búsqueda y multiselección)",
                          cols, default=[])
    for c in slicers:
        nun = int(df[c].nunique(dropna=True))
        if nun > MAX_SLICER_VALUES_WARNING:
            print(f"   · «{c}» tiene {_fmt_int(nun)} valores distintos: la lista será larga (se puede buscar).")
    pcfg["slicers"] = slicers
    pcfg["date_slicer"] = bool(date) and ask_yes_no(f"¿Añadir filtro por rango de fechas sobre «{date}»?", True)
    return pcfg


# ---- capas vectoriales ----------------------------------------------------------
def wizard_layer(path: Path, index: int, cache: dict) -> Optional[dict]:
    layer: Optional[str] = None
    if path.suffix.lower() == ".gpkg":
        names = list_vector_layers(path)
        if len(names) > 1:
            layer = names[ask_choice("El GeoPackage tiene varias capas:", names, 1)]
    lcfg: dict[str, Any] = {"path": str(path), "layer": layer}
    try:
        raw = read_vector_raw(path, layer)
        if raw.crs is None:
            epsg = ask_text("La capa no tiene CRS definido. Introduce el código EPSG", "4326")
            lcfg["crs_assumed"] = f"EPSG:{epsg.replace('EPSG:', '').strip()}"
        gdf = finish_vector(raw, lcfg.get("crs_assumed"))
    except Exception as exc:  # noqa: BLE001
        print(f"   · No se pudo leer la capa ({exc}). Se omite.")
        return None
    cache.setdefault("layers", {})[index] = gdf

    kind = geometry_kind(gdf)
    kind_txt = {"polygon": "polígonos", "line": "líneas", "point": "puntos", "mixed": "geometrías mixtas"}[kind]
    print(f"\n  {_fmt_int(len(gdf))} entidades ({kind_txt}) · {len(visible_columns(gdf))} columnas")
    lcfg["name"] = ask_text("Nombre de la capa", path.stem)
    lcfg["show"] = ask_yes_no("¿Mostrarla activada al abrir el mapa?", True)
    lcfg["style"] = ask_style(gdf, f"«{lcfg['name']}»", "#6a1b9a")

    if kind != "point":
        lcfg["weight"] = ask_number("Grosor del contorno/línea en px", 2.4 if kind == "line" else 1.8, 0.3, 12)
        lcfg["dashed"] = ask_yes_no("¿Trazo discontinuo?", False)
    if kind in ("polygon", "mixed"):
        lcfg["fill_opacity"] = ask_number("Opacidad del relleno (0 = sin relleno, 1 = opaco)", 0.3, 0, 1)

    print("\n  Columnas disponibles:")
    cols = print_columns(gdf)
    first = cols[:1]
    lcfg["tooltip"] = ask_columns("Campos del TOOLTIP (al pasar el ratón)", cols, default=first)
    lcfg["popup"] = ask_columns("Campos del POPUP (al hacer clic)", cols, default=cols[:30])

    nv = int(gdf.geometry.count_coordinates().sum()) if hasattr(gdf.geometry, "count_coordinates") else 0
    if nv > SIMPLIFY_SUGGEST_VERTICES:
        print(f"   · La capa tiene {_fmt_int(nv)} vértices: el HTML puede pesar mucho.")
        tol = ask_number("Tolerancia de simplificación en grados (0 = no simplificar; 0.0005 ≈ 50 m)",
                         0, 0, 1)
        lcfg["simplify"] = tol or None
    return lcfg


# ---- flujo principal del asistente -------------------------------------------------
def run_wizard() -> tuple[dict, dict]:
    print("\n" + "═" * 70)
    print("   ASISTENTE DE MAPAS INTERACTIVOS")
    print("   Responde a las preguntas; Enter acepta el valor entre corchetes.")
    print("═" * 70)
    cfg: dict[str, Any] = {"version": CONFIG_VERSION, "positions": None, "layers": []}
    cache: dict[str, Any] = {"layers": {}}

    step("1 · Dataset de posiciones")
    p = pick_file("Selecciona el dataset de las posiciones:",
                  _file_types(TABULAR_EXT | VECTOR_EXT, "Datos de posiciones"))
    if p:
        cfg["positions"] = wizard_positions(p, cache)
    else:
        print("  Sin posiciones: el mapa mostrará sólo las capas que añadas.")

    step("2 · Capas de polígonos / líneas / puntos")
    initial = str(Path(cfg["positions"]["path"]).parent) if cfg["positions"] else None
    while True:
        n = len(cfg["layers"]) + 1
        if n > 1 and not ask_yes_no("¿Añadir otra capa?", False):
            break
        pth = pick_file("Selecciona el dataset con el polígono que deseas representar:",
                        _file_types(VECTOR_EXT, "Capas vectoriales"), initial)
        if not pth:
            if n == 1 and not cfg["positions"]:
                print("  Necesitas al menos un dataset.")
                continue
            break
        lcfg = wizard_layer(pth, len(cfg["layers"]), cache)
        if lcfg:
            cfg["layers"].append(lcfg)
        elif n == 1 and not cfg["positions"]:
            continue

    if not cfg["positions"] and not cfg["layers"]:
        raise ConfigError("No se ha seleccionado ningún dataset.")

    step("3 · Título y salida")
    cfg["title"] = ask_text("Título del mapa (Enter = sin tarjeta de título)", "")
    if cfg["title"]:
        cfg["subtitle"] = ask_text("Subtítulo (opcional)", "")
        if ask_yes_no("¿Añadir un logo?", False):
            logo = pick_file("Selecciona la imagen del logo:",
                             [("Imágenes", "*.png *.jpg *.jpeg *.svg *.gif *.webp"), ("Todos", "*.*")])
            cfg["logo"] = str(logo) if logo else ""
    first_path = Path((cfg["positions"] or cfg["layers"][0])["path"])
    out = pick_save("Guardar el mapa como…", str(first_path.parent), "mapa_interactivo.html")
    cfg["output"] = str(out)
    cfg["open_browser"] = ask_yes_no("¿Abrir el mapa en el navegador al terminar?", True)

    step("Resumen")
    if cfg["positions"]:
        pc = cfg["positions"]
        print(f"  Posiciones : {Path(pc['path']).name}  · color {_describe_style(pc['style'])}")
        print(f"               tooltip: {', '.join(pc['tooltip']) or '—'}")
        print(f"               selectores: {', '.join(pc['slicers']) or '—'}"
              + ("  + rango de fechas" if pc.get("date_slicer") else ""))
    for i, lc in enumerate(cfg["layers"], 1):
        print(f"  Capa {i}     : {lc['name']}  · color {_describe_style(lc['style'])}")
    print(f"  Salida     : {cfg['output']}")
    if not ask_yes_no("¿Generar el mapa?", True):
        raise UserAbort()
    return cfg, cache


# ============================================================================
# 11. GUARDADO / CARGA DE LA CONFIGURACIÓN
# ============================================================================
def config_path_for(output: Path) -> Path:
    return output.with_suffix(".config.json")


def save_config(cfg: dict, output: Path) -> Path:
    path = config_path_for(output)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_config(path: Path) -> dict:
    if not Path(path).is_file():
        raise ConfigError(f"No existe el archivo de configuración: {path}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"El archivo de configuración no es un JSON válido: {exc}") from exc


# ============================================================================
# 12. MAIN
# ============================================================================
def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Genera un mapa interactivo (HTML) con un asistente guiado.")
    ap.add_argument("--config", type=Path, help="Regenera el mapa desde un .config.json, sin preguntas.")
    ap.add_argument("--posiciones", type=Path,
                    help="Con --config: sustituye el dataset de posiciones por otro con la misma estructura.")
    ap.add_argument("--salida", type=Path, help="Ruta del HTML de salida (sustituye a la configurada).")
    ap.add_argument("--sin-dialogos", action="store_true",
                    help="No abre el explorador de archivos: las rutas se escriben por consola.")
    ap.add_argument("--no-abrir", action="store_true", help="No abre el navegador al terminar.")
    return ap.parse_args(argv)


def _pause() -> None:
    """Evita que la ventana de consola se cierre sola al lanzar el script con doble clic."""
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\n  Pulsa Enter para cerrar…")
    except EOFError:
        pass


def main(argv: Optional[list[str]] = None) -> int:
    global _NO_DIALOGS
    args = parse_args(argv)
    _NO_DIALOGS = args.sin_dialogos
    interactive = args.config is None
    try:
        if interactive:
            cfg, cache = run_wizard()
        else:
            cfg, cache = load_config(args.config), {}
            if args.posiciones:
                if not cfg.get("positions"):
                    raise ConfigError("La configuración no tiene posiciones que sustituir.")
                cfg["positions"]["path"] = str(args.posiciones)
        if args.salida:
            cfg["output"] = str(args.salida)
        cfg.setdefault("output", str(Path.cwd() / "mapa_interactivo.html"))

        saved = build_map(cfg, cache)
        if interactive:
            cp = save_config(cfg, saved)
            print("\n  ✔ Mapa generado:", saved)
            print("  ✔ Respuestas guardadas en:", cp)
            print("    Para repetirlo sin preguntas (o con datos nuevos):")
            print(f'      python "{Path(sys.argv[0]).name}" --config "{cp}" [--posiciones datos_nuevos.xlsx]')
        if cfg.get("open_browser", True) and not args.no_abrir:
            open_in_chrome(saved)
        return 0
    except UserAbort:
        print("\n  Cancelado. No se ha generado ningún mapa.")
        return 130
    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.")
        return 130
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    finally:
        if interactive:
            _pause()


if __name__ == "__main__":
    sys.exit(main())
