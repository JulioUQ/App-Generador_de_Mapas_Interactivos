# -*- coding: utf-8 -*-
"""
Generador de mapas interactivos — interfaz web local (sin código).
Arranque:  streamlit run app.py   (o doble clic en Iniciar_Mapas.bat)

Rendimiento (por qué es ágil):
  * Cada sección es un @st.fragment: al tocar un ajuste solo se repite ESA sección.
  * Lectura de archivos y perfiles de columnas se calculan UNA vez (st.cache_resource).
  * Los archivos subidos se guardan en disco una sola vez.
  * Las secciones comparten su configuración mediante st.session_state; el mapa
    solo se construye al pulsar «Generar mapa».
"""
from __future__ import annotations

import hashlib
import re
import tempfile
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import mapas.core as core

eng = core.eng
PREVIEW_AUTO_MB = 10   # por encima, la vista previa es opcional (enviar mapas pesados al navegador tarda)
PREVIEW_MAX_MB = 40

st.set_page_config(page_title="Generador de mapas", page_icon="🗺️", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1100px; padding-top: 2rem;}
      h1 {font-size: 1.9rem !important;}
      div[data-testid="stTabs"] button p {font-size: 1.02rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- utilidades
def workdir() -> Path:
    if "wd" not in st.session_state:
        st.session_state.wd = Path(tempfile.mkdtemp(prefix="mapas_"))
    return st.session_state.wd


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def short(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", "ignore")).hexdigest()[:8]


def upload_key(uf) -> str:
    """Identificador estable de un archivo subido (cambia solo si el usuario sube otro)."""
    return f"{uf.name}:{uf.size}:{getattr(uf, 'file_id', '')}"


def mostrar_html(html: str, height: int = 720) -> None:
    """Previsualiza el mapa (st.iframe en versiones nuevas; components.html en las antiguas)."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=False)


# --------------------------------------------------------------------------- caché (se calcula una vez)
# cache_resource devuelve el MISMO objeto sin copiarlo (cache_data serializa 160.000 filas en cada clic).
# Es seguro: el motor trabaja siempre sobre copias.
@st.cache_resource(show_spinner="Leyendo el archivo… (solo ocurre la primera vez)", max_entries=4)
def leer_tabla(clave: str, path: str, sheet: str | None):
    return eng.read_table(Path(path), sheet)


@st.cache_resource(show_spinner=False, max_entries=6)
def hojas_excel(clave: str, path: str) -> list[str]:
    return eng.list_sheets(Path(path))


@st.cache_resource(show_spinner="Leyendo la capa…", max_entries=8)
def leer_vector(clave: str, path: str, layer: str | None, assumed: str):
    # `clave` incluye la huella del shapefile completo (.shp + .dbf + .prj…): si llega un
    # acompañante después, la clave cambia y la capa se vuelve a leer con sus atributos.
    raw = eng.read_vector_raw(Path(path), layer)
    return eng.finish_vector(raw, assumed), raw.crs is None


@st.cache_resource(show_spinner="Cargando capa corporativa…", max_entries=8)
def leer_referencia(clave: str, carpeta: str):
    core.set_gis_dir(carpeta)
    return core.cargar_referencia(clave)


@st.cache_resource(show_spinner=False, max_entries=16)
def perfil(clave: str, _df) -> dict:
    """Columnas, tipos y nº de valores distintos: caro de calcular, se hace una sola vez."""
    cols = eng.visible_columns(_df)
    kinds = {c: eng.column_kind(_df[c]) for c in cols}
    nun = {c: int(_df[c].head(50_000).nunique(dropna=True)) for c in cols}
    out = {"cols": cols, "kinds": kinds, "nun": nun}
    if hasattr(_df, "geometry"):  # capa vectorial
        out["kind"] = eng.geometry_kind(_df)
        out["nvert"] = int(_df.geometry.count_coordinates().sum())
    else:  # tabla de posiciones
        out["lat"], out["lon"], out["date"] = eng.guess_lat(_df), eng.guess_lon(_df), eng.guess_date(_df)
    return out


@st.cache_resource(show_spinner=False, max_entries=64)
def conteo(clave: str, col: str, _df):
    return eng.clean_text(_df[col]).value_counts()


@st.cache_resource(show_spinner=False, max_entries=16)
def coords_validas(clave: str, lat: str, lon: str, _df) -> float:
    return float((eng.to_float(_df[lat]).between(-90, 90) & eng.to_float(_df[lon]).between(-180, 180)).mean())


# --------------------------------------------------------------------------- selector de emojis (estilo WhatsApp)
N_TABS_EMOJI = 1 + len(core.EMOJI_CATEGORIAS)      # 0 = recientes, 1.. = categorías


def _emoji_guardar(key: str, valor: str) -> None:
    st.session_state[f"{key}_emoji"] = valor
    if valor:
        rec = [valor] + [e for e in st.session_state.get("emoji_rec", []) if e != valor]
        st.session_state["emoji_rec"] = rec[:16]


def _emoji_limpiar_pestanas(key: str, salvo: int = -1) -> None:
    for j in range(N_TABS_EMOJI):
        if j != salvo:
            st.session_state[f"{key}_pill{j}"] = None


def _emoji_elegido(key: str, i: int) -> None:
    """Se pulsó un emoji en la pestaña i: solo puede haber uno elegido en todo el panel."""
    valor = st.session_state.get(f"{key}_pill{i}")
    _emoji_limpiar_pestanas(key, salvo=i)
    st.session_state[f"{key}_txt"] = ""
    _emoji_guardar(key, valor or "")


def _emoji_escrito(key: str) -> None:
    _emoji_limpiar_pestanas(key)
    _emoji_guardar(key, st.session_state.get(f"{key}_txt", "").strip())


def _emoji_quitar(key: str) -> None:
    _emoji_limpiar_pestanas(key)
    st.session_state[f"{key}_txt"] = ""
    _emoji_guardar(key, "")


def selector_emoji(key: str) -> str:
    """Botón que abre un panel con pestañas de emojis por tipo. Devuelve el emoji elegido ('' si ninguno)."""
    actual = st.session_state.get(f"{key}_emoji", "")
    with st.popover(f"{actual} Cambiar" if actual else "🙂 Elegir", help="Opcional. Si eliges uno, sustituye al símbolo de color: se verá igual en el control de capas y en la leyenda. Sin emoji se usa el símbolo del estilo de la capa."):
        iconos = ["🕒"] + [c[0] for c in core.EMOJI_CATEGORIAS]
        for i, tab in enumerate(st.tabs(iconos)):
            with tab:
                if i == 0:
                    st.caption("Recientes")
                    lista = st.session_state.get("emoji_rec", [])
                    if not lista:
                        st.caption("Aquí aparecerán los últimos emojis que elijas.")
                        continue
                else:
                    st.caption(core.EMOJI_CATEGORIAS[i - 1][1])
                    lista = core.EMOJI_CATEGORIAS[i - 1][2]
                st.pills("Emoji", lista, selection_mode="single", key=f"{key}_pill{i}",
                         label_visibility="collapsed", on_change=_emoji_elegido, args=(key, i))
        c1, c2 = st.columns([3, 2])
        c1.text_input("¿Otro emoji? Escríbelo o pégalo", key=f"{key}_txt", max_chars=8,
                      on_change=_emoji_escrito, args=(key,),
                      help="En Windows, la tecla Windows + punto (.) abre el teclado completo de emojis.")
        c2.write("")
        c2.button("Quitar emoji", key=f"{key}_quitar", on_click=_emoji_quitar, args=(key,), width="stretch")
    return actual


def nombre_y_emoji(key: str, nombre_defecto: str) -> tuple[str, str]:
    """Nombre que verá el usuario del mapa en el control de capas + emoji opcional."""
    c1, c2 = st.columns([4, 1])
    nombre = c1.text_input("Nombre en el control de capas", nombre_defecto, key=f"{key}_name")
    with c2:
        st.caption("Emoji")
        emoji = selector_emoji(key)
    return nombre.strip() or nombre_defecto, emoji


# --------------------------------------------------------------------------- estilo (color)
def default_category_column(pf: dict) -> str:
    """Primera columna de texto con pocas categorías (evita proponer latitud o un identificador)."""
    cols, kinds, nun = pf["cols"], pf["kinds"], pf["nun"]
    ok = [c for c in cols if kinds[c] != "fecha" and 2 <= nun[c] <= eng.MAX_CATEGORIES_WARNING]
    texto = [c for c in ok if kinds[c] == "texto"]
    return (texto or ok or cols)[0]


def style_widget(clave: str, pf: dict, df, key: str, default_color: str, what: str) -> dict:
    """Equivale a ask_style() del asistente de consola. Sirve igual para posiciones y para capas."""
    cols = pf["cols"]
    num_cols = [c for c in cols if pf["kinds"][c] == "número"]
    modos = {"Un solo color": "single", "Por categorías": "category", "Por rangos numéricos": "numeric"}
    if not cols:
        st.info("Esta capa no tiene tabla de atributos, así que solo puede llevar un color. "
                "Si es un shapefile, sube también el archivo .dbf.")
    opciones = list(modos) if cols else ["Un solo color"]
    modo = modos[st.radio(f"Colorear {what}", opciones, horizontal=True, key=f"{key}_modo")]

    if modo == "single":
        return {"mode": "single", "color": st.color_picker("Color", default_color, key=f"{key}_color")}

    if modo == "category":
        col = st.selectbox("Columna que define la categoría", cols,
                           index=cols.index(default_category_column(pf)), key=f"{key}_ccol")
        counts = conteo(clave, col, df)
        cats = [str(c) for c in counts.index]
        if len(cats) > eng.MAX_CATEGORIES_WARNING:
            st.warning(f"«{col}» tiene {len(cats)} categorías: se creará una capa por cada una.")
        colors = eng.assign_colors(cats)
        with st.expander(f"Cambiar colores u ocultar categorías ({len(cats)} categorías)"):
            for c in cats[:20]:
                colors[c] = st.color_picker(f"{c}  ·  {fmt_int(int(counts[c]))}", colors[c],
                                            key=f"{key}_cc_{col}_{c}")
            if len(cats) > 20:
                st.caption(f"Las otras {len(cats) - 20} categorías usan colores automáticos.")
            hidden = st.multiselect("Desactivadas al abrir el mapa", cats[:50], key=f"{key}_hid_{col}")
        return {"mode": "category", "column": col, "colors": colors, "hidden": hidden}

    if not num_cols:
        st.info("No hay columnas numéricas; se usará un solo color.")
        return {"mode": "single", "color": st.color_picker("Color", default_color, key=f"{key}_color2")}
    col = st.selectbox("Columna numérica", num_cols, key=f"{key}_ncol")
    c1, c2 = st.columns(2)
    clases = c1.slider("Número de rangos", 2, 9, 5, key=f"{key}_ncl")
    paleta = c2.selectbox("Paleta", list(eng.RAMPS), key=f"{key}_pal")
    return {"mode": "numeric", "column": col, "classes": clases, "palette": paleta}


# --------------------------------------------------------------------------- 1 · posiciones
def guardar_posicion(up, clave: str) -> Path:
    """Guarda el archivo en disco UNA sola vez (en su propia carpeta, sin pisar a otros)."""
    ruta = workdir() / "posiciones" / short(clave) / Path(up.name).name
    if not ruta.exists():
        core.guardar_archivo(up.name, up.getvalue(), ruta.parent)
    return ruta


def panel_posiciones(idx: int, clave: str, ruta: Path, sheet: str | None, nombre_defecto: str) -> dict | None:
    """Configuración de UN conjunto de posiciones. Devuelve su entrada para el mapa (o None si falla)."""
    try:
        df = leer_tabla(clave, str(ruta), sheet)
        pk = f"{clave}|{sheet}"
        pf = perfil(pk, df)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el archivo: {exc}")
        return None

    kp = f"pos_{short(pk)}"
    cols = pf["cols"]
    st.success(f"{fmt_int(len(df))} filas · {len(cols)} columnas")
    st.dataframe(df.head(8), width="stretch", hide_index=True)

    st.markdown("**¿Qué columnas tienen las coordenadas?**")
    lat_g, lon_g, date_g = pf["lat"], pf["lon"], pf["date"]
    c1, c2, c3 = st.columns(3)
    lat = c1.selectbox("Latitud", cols, index=cols.index(lat_g) if lat_g in cols else 0, key=f"{kp}_lat")
    lon = c2.selectbox("Longitud", cols, index=cols.index(lon_g) if lon_g in cols else min(1, len(cols) - 1),
                       key=f"{kp}_lon")
    fechas = ["(sin fecha)"] + cols
    date = c3.selectbox("Fecha", fechas, index=fechas.index(date_g) if date_g in cols else 0, key=f"{kp}_date")
    date = None if date == "(sin fecha)" else date

    if coords_validas(pk, lat, lon, df) < 0.5:
        st.warning("Menos de la mitad de las filas tiene coordenadas válidas. ¿Están intercambiadas latitud y longitud?")

    st.divider()
    nombre, emoji = nombre_y_emoji(kp, nombre_defecto)
    color_defecto = eng.CATEGORY_PALETTE[idx % len(eng.CATEGORY_PALETTE)]
    style = style_widget(pk, pf, df, f"{kp}_st", color_defecto, "los puntos")
    radio = st.slider("Tamaño de los puntos", 0.5, 15.0, float(eng.DEFAULT_POINT_RADIUS), 0.1, key=f"{kp}_rad")

    otras = [c for c in cols if c not in (lat, lon)]
    c1, c2 = st.columns(2)
    tooltip = c1.multiselect("Al pasar el ratón por un punto, mostrar…", cols, default=otras[:3], key=f"{kp}_tip")
    popup = c2.multiselect("Al hacer clic en un punto, mostrar…", cols, default=otras[:30], key=f"{kp}_pop")
    slicers = st.multiselect("Filtros desplegables (como en Power BI)", cols, key=f"{kp}_sl",
                             help="Cada columna elegida añade una lista con búsqueda y selección múltiple. Los filtros se condicionan entre sí: las opciones que se quedan sin posiciones con el resto de filtros (o con capas apagadas en el control de capas) aparecen en gris.")
    date_slicer = bool(date) and st.checkbox(f"Filtro por rango de fechas sobre «{date}»", True, key=f"{kp}_ds")

    max_points = None
    if len(df) > eng.MAX_POINTS_WARNING:
        st.warning(f"Hay {fmt_int(len(df))} posiciones: el mapa puede pesar y ir lento.")
        mx = st.number_input("Reducir a este número de puntos (0 = todos)", 0, len(df), 0, key=f"{kp}_mx")
        max_points = int(mx) or None

    return {"clave": clave, "path": str(ruta), "sheet": sheet,
            "pcfg": {"path": str(ruta), "sheet": sheet, "lat": lat, "lon": lon, "date": date,
                     "name": nombre, "emoji": emoji, "style": style, "radius": radio,
                     "tooltip": tooltip, "popup": popup, "slicers": slicers,
                     "date_slicer": date_slicer, "max_points": max_points}}


@st.fragment
def ui_posiciones() -> None:
    st.markdown("Archivos con una fila por posición (Excel, CSV, Parquet, GeoPackage o GeoJSON de puntos). "
                "Puedes añadir **varios conjuntos de datos**: cada uno se configura por separado y se dibuja como "
                "capas distintas, con su propia leyenda y sus propios filtros. Es opcional: puedes hacer un mapa solo con capas.")
    ups = st.file_uploader("Archivos de posiciones", accept_multiple_files=True, key="up_pos",
                           type=["xlsx", "xlsm", "xls", "csv", "tsv", "txt", "parquet", "gpkg", "geojson"])

    # Un conjunto por archivo (y por hoja, si un Excel tiene varias y el usuario las elige)
    datasets: list[tuple[str, Path, str | None, str]] = []   # (clave, ruta, hoja, nombre por defecto)
    for up in ups:
        clave = upload_key(up)
        try:
            ruta = guardar_posicion(up, clave)
            hojas = []
            if ruta.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
                hojas = hojas_excel(clave, str(ruta))
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo leer «{up.name}»: {exc}")
            continue
        if len(hojas) > 1:
            elegidas = st.multiselect(f"Hojas de «{up.name}» que quieres usar (cada hoja es un conjunto distinto)",
                                      hojas, default=hojas[:1], key=f"hojas_{short(clave)}")
            for h in elegidas:
                datasets.append((clave, ruta, h, f"{Path(up.name).stem} · {h}"))
        else:
            datasets.append((clave, ruta, hojas[0] if hojas else None, Path(up.name).stem))

    if len(datasets) > 1:
        st.info("Con varios conjuntos, cada filtro del mapa llevará delante el nombre de su conjunto "
                "y solo actuará sobre sus propios puntos.")

    resultado: list[dict] = []
    for idx, (clave, ruta, sheet, nombre_def) in enumerate(datasets):
        etiqueta = f"📄 {nombre_def}"
        with st.expander(etiqueta, expanded=len(datasets) == 1):
            entrada = panel_posiciones(idx, clave, ruta, sheet, nombre_def)
        if entrada:
            resultado.append(entrada)
    st.session_state["pos_list"] = resultado


# --------------------------------------------------------------------------- 2 · capas
@st.fragment
def ui_capas() -> None:
    st.markdown("#### Capas de referencia de la empresa")
    refs: list[str] = []
    refs_show: dict[str, bool] = {}
    cols_ref = st.columns(2)
    for i, (clave, ref) in enumerate(core.REFERENCIAS.items()):
        with cols_ref[i % 2]:
            if st.checkbox(ref["label"], False, key=f"ref_{clave}"):
                refs.append(clave)
                refs_show[clave] = st.checkbox("Activa al abrir el mapa", True, key=f"ref_{clave}_show")
    if refs:
        st.caption("Aparecen en el control de capas y comparten un único apartado en la leyenda («Capas geográficas auxiliares»). "
                   "Marca cuáles empiezan activas y cuáles desactivadas. Se dibujan debajo de tus datos (GSA verde oliva, ZEE rojo "
                   "discontinuo, FAO azul), salvo Países, que va siempre por encima de los puntos.")
    st.session_state["refs_sel"] = refs
    st.session_state["refs_show"] = refs_show

    st.markdown("#### Tus propias capas")
    st.markdown("Polígonos, líneas o puntos (shapefile, GeoPackage, GeoJSON, KML…). "
                "Con el botón, elige el **.shp** y la aplicación coge sola el resto de sus archivos "
                "(.dbf, .prj, .shx, .cpg…) de la misma carpeta.")

    # --- Opción principal: elegir desde el disco (se conoce la carpeta, así que se detectan los acompañantes)
    if st.button("📂 Elegir capas del disco…", type="primary", key="btn_disco",
                 help="Abre el selector de archivos de Windows. Puedes marcar varias capas a la vez."):
        try:
            with st.spinner("Elige los archivos en la ventana que se ha abierto (puede estar detrás del navegador)…"):
                elegidas = core.elegir_capas_del_disco(st.session_state.get("capas_dir"))
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo abrir el selector de archivos del sistema ({exc}). "
                     "Usa la opción de arrastrar archivos que hay más abajo.")
        else:
            if elegidas:
                nuevas = [str(r) for r in elegidas]
                st.session_state["capas_dir"] = str(elegidas[0].parent)
                st.session_state["capas_disco_opts"] = list(dict.fromkeys(
                    st.session_state.get("capas_disco_opts", []) + nuevas))
                st.session_state["capas_disco_sel"] = list(dict.fromkeys(
                    st.session_state.get("capas_disco_sel", []) + nuevas))

    opciones = st.session_state.get("capas_disco_opts", [])
    if opciones:
        elegidas_disco = st.multiselect("Capas elegidas del disco (quita las que no quieras)", opciones,
                                        key="capas_disco_sel")
    else:
        elegidas_disco = []

    # Se copian a la carpeta de trabajo solo cuando cambia la selección o algún archivo en disco
    firma = core.firma_disco(elegidas_disco)
    if st.session_state.get("capas_disco_firma") != firma:
        rutas_disco: list[Path] = []
        if elegidas_disco:
            try:
                rutas_disco = core.importar_desde_disco(elegidas_disco, workdir() / "capas_disco")
            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudieron preparar los archivos: {exc}")
        st.session_state["capas_disco_firma"] = firma
        st.session_state["capas_disco_paths"] = [str(r) for r in rutas_disco]
    paths_disco = [Path(r) for r in st.session_state.get("capas_disco_paths", [])]
    if elegidas_disco and not paths_disco:
        st.warning("No encuentro ninguna capa en lo que has elegido.")

    # --- Alternativa: arrastrar archivos (el navegador solo envía los que marques; no ve la carpeta)
    with st.expander("Otra forma: arrastrar o subir archivos"):
        st.caption("El navegador solo envía los archivos que marques, así que de un shapefile hay que marcar "
                   "todos a la vez (.shp .dbf .shx .prj .cpg), o subirlo comprimido en un **.zip**. "
                   "Con el botón de arriba no hace falta.")
        ups = st.file_uploader("Añadir capas", accept_multiple_files=True, key="up_layers",
                               type=["shp", "dbf", "shx", "prj", "cpg", "zip", "gpkg", "geojson", "json", "kml", "gml", "fgb"])

    # Los archivos se guardan en disco solo cuando cambia lo subido (no en cada clic)
    sig = tuple((u.name, u.size, getattr(u, "file_id", "")) for u in ups)
    if st.session_state.get("capas_sig") != sig:
        paths: list[Path] = []
        if ups:
            try:
                paths = core.guardar_subidas([(u.name, u.getvalue()) for u in ups], workdir() / "capas")
            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudieron preparar los archivos: {exc}")
        st.session_state["capas_sig"] = sig
        st.session_state["capas_paths"] = [str(p) for p in paths]
    paths_subidas = [Path(p) for p in st.session_state.get("capas_paths", [])]
    if ups and not paths_subidas:
        st.warning("No encuentro ninguna capa en lo que has subido (¿falta el .shp?).")
    paths = paths_disco + paths_subidas
    carpeta_disco = workdir() / "capas_disco"

    user_layers: list[dict] = []
    for pth in paths:
        huella = core.huella(pth)                      # cambia si llega un .dbf/.prj después del .shp
        vclave = f"{pth}|{huella}"
        key = f"lay_{short(str(pth))}"
        with st.expander(f"📄 {pth.name}", expanded=len(paths) == 1):
            layer = None
            falta = core.archivos_que_faltan(pth)
            del_disco = carpeta_disco in pth.parents
            if ".dbf" in falta:
                if del_disco:
                    st.warning("No hay ningún archivo **.dbf** (tabla de atributos) junto al .shp, en su carpeta original. "
                               "Sin él no podrás elegir atributos para mostrar ni colorear por categorías.")
                else:
                    st.warning("Todavía no has subido el archivo **.dbf** (tabla de atributos). Sin él no podrás elegir "
                               "atributos para mostrar ni colorear por categorías. Súbelo junto al .shp, o usa el botón "
                               "«Elegir capas del disco» para que se detecte solo.")
            if ".prj" in falta:
                st.info("Falta el archivo .prj (sistema de coordenadas): se te pedirá el código EPSG."
                        if del_disco else
                        "Falta el archivo .prj (sistema de coordenadas): se te pedirá el código EPSG hasta que lo subas.")
            if ".shx" in falta:
                st.caption("El .shx no es imprescindible: se reconstruye automáticamente.")
            if pth.suffix.lower() == ".gpkg":
                nombres = eng.list_vector_layers(pth)
                if len(nombres) > 1:
                    layer = st.selectbox("El GeoPackage tiene varias capas", nombres, key=f"{key}_gl")
            assumed = "EPSG:4326"
            try:
                gdf, sin_crs = leer_vector(vclave, str(pth), layer, assumed)
                if sin_crs:
                    epsg = st.text_input("La capa no trae sistema de coordenadas. Código EPSG", "4326", key=f"{key}_epsg")
                    assumed = f"EPSG:{epsg.replace('EPSG:', '').strip()}"
                    gdf, _ = leer_vector(vclave, str(pth), layer, assumed)
                pf = perfil(f"{vclave}|{layer}|{assumed}", gdf)
            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudo leer esta capa: {exc}")
                continue

            kind = pf["kind"]
            st.caption(f"{fmt_int(len(gdf))} elementos · {len(pf['cols'])} atributos · "
                       f"{dict(polygon='polígonos', line='líneas', point='puntos', mixed='geometrías mixtas')[kind]}")
            lcfg = {"path": str(pth), "layer": layer, "crs_assumed": assumed}
            lcfg["name"], lcfg["emoji"] = nombre_y_emoji(key, pth.stem)
            lcfg["show"] = st.checkbox("Visible al abrir el mapa", True, key=f"{key}_show")
            lcfg["style"] = style_widget(f"{vclave}|{layer}|{assumed}", pf, gdf, f"{key}_st", "#6a1b9a", "la capa")
            if kind != "point":
                c1, c2 = st.columns(2)
                lcfg["weight"] = c1.slider("Grosor de línea", 0.3, 12.0, 2.4 if kind == "line" else 1.8, 0.1, key=f"{key}_w")
                lcfg["dashed"] = c2.checkbox("Trazo discontinuo", False, key=f"{key}_da")
            if kind in ("polygon", "mixed"):
                lcfg["fill_opacity"] = st.slider("Opacidad del relleno", 0.0, 1.0, 0.3, 0.05, key=f"{key}_fo")
            gcols = pf["cols"]
            c1, c2 = st.columns(2)
            lcfg["tooltip"] = c1.multiselect("Al pasar el ratón, mostrar…", gcols, default=gcols[:1], key=f"{key}_tip")
            lcfg["popup"] = c2.multiselect("Al hacer clic, mostrar…", gcols, default=gcols[:30], key=f"{key}_pop")
            if pf["nvert"] > eng.SIMPLIFY_SUGGEST_VERTICES:
                st.warning(f"La capa tiene {fmt_int(pf['nvert'])} vértices; el mapa pesará mucho.")
                tol = st.number_input("Simplificar (grados; 0.0005 ≈ 50 m, 0 = no)", 0.0, 1.0, 0.0005,
                                      format="%.4f", key=f"{key}_simp")
                lcfg["simplify"] = tol or None
            user_layers.append({"lcfg": lcfg, "vclave": vclave, "path": str(pth), "layer": layer, "assumed": assumed})
    st.session_state["user_layers"] = user_layers


# --------------------------------------------------------------------------- 3 · título y generar
@st.fragment
def ui_titulo() -> None:
    c1, c2 = st.columns(2)
    titulo = c1.text_input("Título del mapa (opcional)", "", key="titulo")
    subtitulo = c2.text_input("Subtítulo (opcional)", "", key="subtitulo") if titulo else ""
    logo_path = ""
    if titulo:
        logo = st.file_uploader("Logo (opcional)", type=["png", "jpg", "jpeg", "svg", "gif", "webp"], key="up_logo")
        if logo:
            logo_path = str(core.guardar_archivo(logo.name, logo.getvalue(), workdir() / "logo"))
    st.session_state["titulos"] = {"title": titulo, "subtitle": subtitulo, "logo": logo_path}


def generar_mapa() -> None:
    pos = st.session_state.get("pos_list", [])
    refs = st.session_state.get("refs_sel", [])
    refs_show = st.session_state.get("refs_show", {})
    user = st.session_state.get("user_layers", [])
    tit = st.session_state.get("titulos", {"title": "", "subtitle": "", "logo": ""})
    carpeta = st.session_state.get("carpeta", str(core.gis_dir()))
    if not (pos or refs or user):
        st.warning("Sube un archivo de posiciones o añade al menos una capa para poder generar el mapa.")
        return

    t0 = time.time()
    layers_cfg: list[dict] = []
    cache: dict = {"layers": {}, "positions_raws": {}}
    try:
        with st.spinner("Preparando capas…"):
            for clave in refs:
                try:
                    gdf = leer_referencia(clave, carpeta)
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"No se pudo cargar «{core.REFERENCIAS[clave]['label']}» "
                               f"(¿está accesible la carpeta {carpeta}?). Se omite. Detalle: {exc}")
                    continue
                cache["layers"][len(layers_cfg)] = gdf
                layers_cfg.append(core.lcfg_referencia(clave, refs_show.get(clave, True)))
            for u in user:
                gdf, _ = leer_vector(u["vclave"], u["path"], u["layer"], u["assumed"])
                cache["layers"][len(layers_cfg)] = gdf
                layers_cfg.append(u["lcfg"])
            for k, p in enumerate(pos):
                cache["positions_raws"][k] = leer_tabla(p["clave"], p["path"], p["sheet"])

        cfg = {"version": eng.CONFIG_VERSION, "positions": [p["pcfg"] for p in pos] or None, "layers": layers_cfg,
               "title": tit["title"], "subtitle": tit["subtitle"], "logo": tit["logo"],
               "output": str(workdir() / "mapa_interactivo.html")}
        with st.spinner("Generando el mapa…"):
            salida = core.generar_mapa(cfg, cache)
        html = salida.read_text(encoding="utf-8")
        base = re.sub(r"[^\w\-]+", "_", tit["title"]).strip("_") or "mapa_interactivo"
        script, datos = None, []
        try:   # el script es un extra: si falla, el mapa se entrega igualmente
            script, datos = core.generar_script(cfg, carpeta, base + ".html")
        except Exception as exc:  # noqa: BLE001
            st.warning(f"El mapa está listo, pero no se pudo preparar el script .py. Detalle: {exc}")
        st.session_state["result"] = {
            "html": html, "bytes": len(html.encode("utf-8")), "secs": time.time() - t0,
            "stats": cache.get("stats", []), "name": base + ".html",
            "script": script, "script_name": f"generar_{base}.py", "datos": datos}
    except eng.ConfigError as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))
    except Exception as exc:  # noqa: BLE001
        st.session_state.pop("result", None)
        st.error("Algo ha fallado al generar el mapa. Revisa las columnas elegidas.")
        st.exception(exc)


def resumen_filas(stats: list[dict]) -> None:
    """Cuántas filas se leyeron, cuántas se descartaron y cuántas se dibujaron en cada conjunto."""
    if not stats:
        return
    with st.expander("Resumen de filas dibujadas", expanded=any(s["n_invalidas"] for s in stats)):
        for s in stats:
            linea = (f"**{s['name']}**: {fmt_int(s['n_leidas'])} filas en el archivo → "
                     f"**{fmt_int(s['n_dibujadas'])} puntos dibujados**")
            if s["n_invalidas"]:
                linea += f" · {fmt_int(s['n_invalidas'])} descartadas por tener latitud/longitud vacía o fuera de rango"
            reducidas = s["n_leidas"] - s["n_invalidas"] - s["n_dibujadas"]
            if reducidas > 0:
                linea += f" · {fmt_int(reducidas)} omitidas por el límite de puntos que indicaste"
            st.markdown(linea)
        st.caption("Los números entre paréntesis del mapa (leyenda y control de capas) son el nº de puntos "
                   "(o elementos, en una capa) de cada grupo; no cambian al usar los filtros. En cambio, el mensaje «X de Y posiciones visibles» del mapa sí se actualiza con cada filtro y con las capas que enciendas o apagues.")


@st.fragment
def ui_generar() -> None:
    if st.button("🗺️ Generar mapa", type="primary"):
        generar_mapa()

    res = st.session_state.get("result")
    if res:
        mb = res["bytes"] / 1e6
        st.success(f"Mapa listo en {res['secs']:.0f} s ({mb:.1f} MB). Descárgalo y ábrelo en tu navegador, "
                   "o envíalo por correo: es un único archivo.")
        resumen_filas(res.get("stats", []))
        st.download_button("⬇️ Descargar mapa (HTML)", res["html"].encode("utf-8"), file_name=res["name"],
                           mime="text/html", type="primary", on_click="ignore")
        if res.get("script"):
            st.download_button("⬇️ Descargar script (.py) para regenerar este mapa", res["script"].encode("utf-8"),
                               file_name=res["script_name"], mime="text/x-python", on_click="ignore",
                               help="Un único archivo con todo el código necesario y la configuración elegida.")
            datos = res.get("datos") or []
            st.caption("El script espera tus datos en una carpeta **datos** junto a él"
                       + (": " + ", ".join(f"`{d}`" for d in datos) + ". " if datos else ". ")
                       + "Si hay shapefiles, copia también su .dbf, .prj y .shx. "
                         "Para ejecutarlo hace falta Python 3.10+ con folium, geopandas, pandas, numpy y openpyxl.")
        if mb > PREVIEW_MAX_MB:
            st.info(f"El mapa pesa más de {PREVIEW_MAX_MB} MB y no se previsualiza aquí; descárgalo para verlo.")
        elif mb <= PREVIEW_AUTO_MB or st.checkbox("Mostrar vista previa aquí (el mapa es pesado y puede ir lenta)", False):
            mostrar_html(res["html"])
        else:
            st.caption("Vista previa desactivada por el tamaño del mapa: descárgalo y ábrelo en el navegador.")


# --------------------------------------------------------------------------- página
st.title("🗺️ Generador de mapas interactivos")
st.caption("Sube tus datos, elige cómo quieres verlos y descarga un mapa HTML que se abre en cualquier navegador.")

with st.sidebar:
    st.subheader("Cómo se usa")
    st.markdown(
        "1. **Posiciones**: sube uno o varios Excel/CSV con latitud y longitud.\n"
        "2. **Capas**: añade zonas (GSA, FAO, ZEE…) o tus propios polígonos.\n"
        "3. **Título y mapa**: ponle nombre y pulsa *Generar*.\n\n"
        "Todo se procesa en tu ordenador; nada se envía a internet."
    )
    with st.expander("Ajustes avanzados"):
        st.text_input("Carpeta de capas corporativas (GIS)", value=str(core.gis_dir()), key="carpeta",
                      help="Debe contener ZonasGSA, ZonasFAO, ZonasZEE y WorldCountries.")

tab_pos, tab_capas, tab_out = st.tabs(["① Posiciones", "② Capas", "③ Título y mapa"])
with tab_pos:
    ui_posiciones()
with tab_capas:
    ui_capas()
with tab_out:
    ui_titulo()
    st.divider()
    ui_generar()
