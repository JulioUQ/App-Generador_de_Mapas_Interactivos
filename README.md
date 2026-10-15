# Generador de Mapas Interactivos

Aplicación local para crear mapas web interactivos (un único archivo HTML autocontenido) a partir de posiciones, capas geográficas propias y capas geográficas auxiliares corporativas. No requiere programar.

## Requisitos

- Python 3.10 o superior (se usa sintaxis `X | None`).
- Paquetes: `streamlit`, `folium`, `geopandas`, `pandas`, `numpy`, `openpyxl` (Excel). Parquet requiere además `pyarrow`.
- `tkinter` (incluido con Python en Windows) para el botón «Elegir capas del disco».

## Instalación y ejecución

La forma más sencilla de iniciar la aplicación es ejecutar:

```text
iniciar_mapas.bat
```

La primera ejecución prepara automáticamente el entorno virtual e instala las dependencias necesarias. Este proceso puede tardar unos minutos.

Una vez iniciado el sistema, se abrirá automáticamente el navegador con la aplicación.

## Qué ofrece

- **Posiciones**: Excel, CSV, Parquet o puntos en GPKG/SHP/GeoJSON. Se pueden cargar varios conjuntos a la vez,
  cada uno con su leyenda y sus filtros.
- **Capas propias**: polígonos, líneas o puntos (SHP, GPKG, GeoJSON, KML, GML, FGB, ZIP). Al elegir un `.shp` desde
  el disco se recogen solos sus archivos asociados (`.dbf`, `.prj`, `.shx`, `.cpg`…).
- **Capas geográficas auxiliares** (corporativas, vía `geo_functions.py`): GSA, ZEE, FAO y Países.
  - Aparecen en el control de capas; el usuario elige cuáles arrancan activas.
  - Comparten un único apartado en la leyenda: «Capas geográficas auxiliares».
  - Países se dibuja siempre por encima de los puntos; el resto, por debajo.
- **Estilo**: color único, por categorías o por rangos numéricos; emoji opcional como icono en control de capas y leyenda.
- **Interactividad en el mapa**: tooltips y popups configurables, selectores de filtro con búsqueda, filtro por fechas,
  control de capas, leyenda, minimapa y coordenadas del cursor.
- **Salida**: HTML que se abre en cualquier navegador, con título, subtítulo y logo opcionales.
  
## Uso

La aplicación está organizada en tres pestañas principales.

Sigue el flujo de trabajo indicado en las pestañas **1, 2 y 3**.

## Configuración de capas GIS

La aplicación utiliza diferentes capas geoespaciales, como:

* GSA
* FAO
* ZEE
* Países

Si estas capas se encuentran en una ubicación diferente a la configurada por defecto, puedes modificar su ubicación desde:

**Ajustes avanzados → Ruta de las capas GIS**

## Estructura del proyecto

| Archivo | Función |
|---|---|
| `app.py` | Interfaz web (Streamlit) en tres pestañas: Posiciones, Capas, Título y mapa. |
| `core.py` | Capa intermedia: definición de capas auxiliares, subidas de archivos, selector de disco. |
| `motor.py` | Motor que construye el mapa (Folium/Leaflet). También funciona por consola. |
| `geo.py` | Carga de las capas GIS corporativas y utilidades geoespaciales. |

## Dependencias

Las dependencias del proyecto se encuentran en:

```text
requirements.txt
```

## Inicio rápido

Para iniciar la aplicación:

1. Instala Python 3.10 o superior.
2. Asegúrate de que Python está disponible en el PATH.
3. Ejecuta `iniciar_mapas.bat`.
4. Espera a que se prepare el entorno la primera vez.
5. Accede a la aplicación desde el navegador.

## Uso

Interfaz web:

```bash
streamlit run app.py
```

Consola (asistente guiado o regeneración desde una configuración guardada):

```bash
python generar_mapa_asistente.py
python generar_mapa_asistente.py --config mapa.config.json
python generar_mapa_asistente.py --config mapa.config.json --posiciones datos_nuevos.xlsx
```

Opciones: `--salida RUTA.html`, `--sin-dialogos`, `--no-abrir`.

## Capas corporativas

`geo_functions.py` lee los shapefiles de `GIS_DIR` (subcarpetas `WorldCountries`, `ZonasGSA`, `ZonasFAO`, `ZonasZEE`).
La ruta se puede cambiar sin tocar código con la variable de entorno `MAPAS_GIS_DIR`, o desde el campo
«Carpeta de capas corporativas (GIS)» de la aplicación. Si la carpeta no es accesible, la capa se omite con un aviso.
