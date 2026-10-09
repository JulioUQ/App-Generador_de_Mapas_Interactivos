
# ================================
# geo_functions.py
# Funciones para análisis de geodatos
# ================================

import sys
import os
import glob
import warnings
from typing import Dict
import pandas as pd
import geopandas as gpd
from shapely import wkt  
from shapely.geometry import Point, Polygon, MultiPolygon
from pathlib import Path

# Añadir directorio raíz al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
warnings.simplefilter(action='ignore', category=UserWarning)

# ====================================
# CAPAS UTILES PARA MAPAS
# ====================================
# Carpeta de las capas GIS corporativas. Se puede cambiar sin tocar el codigo
# definiendo la variable de entorno MAPAS_GIS_DIR.
GIS_DIR = Path(os.environ.get(
    "MAPAS_GIS_DIR",
    r"P:\Proyectos\CALCULO_CIERRES\CONTROL CALIDAD\TeoríaSIPE\Programacion\Directorio GIS con QGIS\GIS_2.0",
))

def gdf_paises() -> gpd.GeoDataFrame:
    """Carga capa de países del mundo como GeoDataFrame en EPSG:4326."""
    ruta_paises = GIS_DIR / "WorldCountries" / "WorldCountries.shp"
    ruta_paises = Path(str(ruta_paises))  # fuerza codificación compatible
    gdf = gpd.read_file(str(ruta_paises))
    return gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)


def gdf_gsa() -> gpd.GeoDataFrame:
    """Carga capa de GSA como GeoDataFrame en EPSG:4326."""
    ruta_gsa = GIS_DIR / "ZonasGSA" / "ZonasGSA.shp"
    ruta_gsa = Path(str(ruta_gsa))  # fuerza codificación compatible
    gdf = gpd.read_file(ruta_gsa)
    return gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)

def gdf_FAO() -> gpd.GeoDataFrame:
    """Carga capa de FAO como GeoDataFrame en EPSG:4326."""
    ruta_fao = GIS_DIR / "ZonasFAO" / "ZonasFAO.shp"
    ruta_fao = Path(str(ruta_fao))  # fuerza codificación compatible
    gdf = gpd.read_file(ruta_fao)
    return gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)

def gdf_ZEE() -> gpd.GeoDataFrame:
    """Carga capa de ZEE como GeoDataFrame en EPSG:4326."""
    ruta_zee = GIS_DIR / "ZonasZEE" / "ZonasZEE.shp"
    ruta_zee = Path(str(ruta_zee))  # fuerza codificación compatible
    gdf = gpd.read_file(ruta_zee)
    return gdf.to_crs(epsg=4326) if gdf.crs else gdf.set_crs(epsg=4326)

# ====================================
# FUNCIONES DE GEOPANDAS / ESPACIALES
# ====================================

def import_shp_as_gpd(shapefile: str) -> gpd.GeoDataFrame:
    """
    Importa shapefile como GeoDataFrame en CRS EPSG:4326
    y lo deja preparado para usar en Folium (sin errores JSON).
    
    Ejemplo:
        gdf = import_shp_as_gpd("/ruta/archivo.shp")
    """
    
    # 1️ Leer shapefile
    gdf = gpd.read_file(shapefile)

    # 2️ Asegurar CRS WGS84 (EPSG:4326)
    if gdf.crs:
        gdf = gdf.to_crs(epsg=4326)
    else:
        gdf = gdf.set_crs(epsg=4326)

    # 3️ Limpiar columnas para evitar error JSON en Folium
    for col in gdf.columns:
        if col != "geometry":
            
            # Convertir datetime a string
            if pd.api.types.is_datetime64_any_dtype(gdf[col]):
                gdf[col] = gdf[col].astype(str)
            
            # Convertir posibles Timestamp sueltos
            elif gdf[col].apply(lambda x: isinstance(x, pd.Timestamp)).any():
                gdf[col] = gdf[col].astype(str)

            # Reemplazar NaN / NaT por None (JSON compatible)
            gdf[col] = gdf[col].where(gdf[col].notnull(), None)

    return gdf

def pd_to_gpd(
    df: pd.DataFrame,
    longitud_col: str = "longitude",
    latitud_col: str = "latitude",
    wkt_col: str = "Geom"
) -> gpd.GeoDataFrame:
    """
    Convierte un DataFrame a GeoDataFrame.
    - Si tiene columnas de lat/lon, crea puntos.
    - Si tiene una columna WKT (por defecto 'Geom'), la convierte a geometría shapely.
    - Devuelve siempre un GeoDataFrame con CRS = EPSG:4326.
    """

    df = df.copy()

    # Caso 1: columnas latitud/longitud
    if longitud_col in df.columns and latitud_col in df.columns:
        geometry = [Point(xy) for xy in zip(df[longitud_col], df[latitud_col])]
        return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    # Caso 2: columna WKT (Geom por defecto)
    if wkt_col in df.columns and df[wkt_col].dtype == "object":
        try:
            df["geometry"] = df[wkt_col].apply(wkt.loads) # type: ignore
            return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        except Exception as e:
            raise ValueError(f"No se pudo convertir la columna '{wkt_col}' desde WKT: {e}")

    # Caso 3: columna 'geometry' en WKT
    if "geometry" in df.columns and df["geometry"].dtype == "object":
        try:
            df["geometry"] = gpd.GeoSeries.from_wkt(df["geometry"])
            return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
        except Exception as e:
            raise ValueError(f"No se pudo convertir la columna 'geometry' desde WKT: {e}")

    raise ValueError("No se encontraron columnas de lat/lon, ni WKT en 'Geom', ni geometría en WKT.")



def drop_z(geom):
    """Convertir geometrías a 2D eliminando coordenada Z

    Ejemplo:
        gdf["geometry"] = gdf["geometry"].apply(drop_z)
    """
    if geom is None:
        return None
    if isinstance(geom, Polygon):
        return Polygon(
            [(x, y) for x, y, *_ in geom.exterior.coords],
            [ [(x, y) for x, y, *_ in ring.coords] for ring in geom.interiors ]
        )
    elif isinstance(geom, MultiPolygon):
        return MultiPolygon([drop_z(p) for p in geom.geoms])
    return geom


def exportar_gdf_shapefile(gdf: gpd.GeoDataFrame, path_out: str, overwrite: bool = True) -> None:
    """Exporta un GeoDataFrame a shapefile en EPSG:4326.

    Ejemplo:
        exportar_gdf_shapefile(gdf, "./salida.shp")
    """
    if gdf.empty:
        raise ValueError("GeoDataFrame vacío.")
    if not gdf.geometry.is_valid.all():
        raise ValueError("Geometrías inválidas.")

    path_out = os.path.abspath(path_out)
    if os.path.exists(path_out) and not overwrite:
        raise FileExistsError(f"'{path_out}' ya existe y overwrite=False.")

    gdf.to_crs(epsg=4326).to_file(path_out, driver='ESRI Shapefile', encoding='utf-8')


def cargar_shapefiles_directorio(directorio: str) -> Dict[str, gpd.GeoDataFrame]:
    """
    Carga todos los archivos .shp de un directorio.
    
    Args:
        directorio: Ruta del directorio con los shapefiles
        
    Returns:
        Diccionario donde las claves son los nombres de archivo (sin extensión)
        y los valores son GeoDataFrames
        
    Ejemplo:
        gdfs = cargar_shapefiles_directorio("/ruta/mi_directorio")
        print(f"Se cargaron {len(gdfs)} shapefiles")
        
        # Acceder a un shapefile específico
        gdf_ejemplo = gdfs["nombre_archivo"]
        
        # Iterar sobre todos
        for nombre, gdf in gdfs.items():
            print(f"{nombre}: {len(gdf)} features")
    """
    
    # Verificar que el directorio existe
    if not os.path.exists(directorio):
        raise FileNotFoundError(f"El directorio '{directorio}' no existe")
    
    if not os.path.isdir(directorio):
        raise NotADirectoryError(f"'{directorio}' no es un directorio")
    
    # Buscar todos los archivos .shp
    patron = os.path.join(directorio, "*.shp")
    archivos_shp = glob.glob(patron)
    
    if not archivos_shp:
        print(f"⚠️ No se encontraron archivos .shp en '{directorio}'")
        return {}
    
    # Cargar cada shapefile
    geodataframes = {}
    errores = []
    
    for ruta_shp in archivos_shp:
        nombre_archivo = os.path.splitext(os.path.basename(ruta_shp))[0]
        
        try:
            gdf = import_shp_as_gpd(ruta_shp)
            geodataframes[nombre_archivo] = gdf
            print(f"✓ Cargado: {nombre_archivo} ({len(gdf)} features, CRS: {gdf.crs})")
            
        except Exception as e:
            error_msg = f"✗ Error al cargar '{nombre_archivo}': {str(e)}"
            errores.append(error_msg)
            print(error_msg)
    
    # Resumen
    print(f"\n{'='*60}")
    print(f"Resumen: {len(geodataframes)}/{len(archivos_shp)} shapefiles cargados correctamente")
    if errores:
        print(f"Errores: {len(errores)}")
    print(f"{'='*60}\n")
    
    return geodataframes