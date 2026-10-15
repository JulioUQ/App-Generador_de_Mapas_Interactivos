# Generador de mapas interactivos — Resumen corporativo

**Estado:** versión de trabajo · **Tipo:** herramienta interna de escritorio (ejecución local)

## Propósito

Permitir que cualquier usuario del área convierta sus datos de posiciones y capas geográficas en un mapa
interactivo, sin conocimientos de programación ni de GIS, y lo comparta como un único archivo.

## Valor para el negocio

- **Autonomía**: el usuario genera sus propios mapas en minutos, sin depender de un especialista.
- **Coherencia**: las capas corporativas (GSA, ZEE, FAO, Países) se usan siempre con el mismo estilo y la misma fuente.
- **Distribución sencilla**: el resultado es un HTML que se abre en cualquier navegador, sin instalar nada ni conectarse a servidores propios.
- **Reutilización**: la configuración puede guardarse y regenerarse con datos nuevos de la misma estructura.

## Capacidades actuales

- Carga de posiciones desde Excel, CSV, Parquet o formatos geográficos, con varios conjuntos en un mismo mapa.
- Incorporación de capas propias (SHP, GPKG, GeoJSON, KML y otros) con detección automática de los archivos asociados.
- Capas geográficas auxiliares corporativas, activables desde el control de capas del mapa y agrupadas en un único apartado de la leyenda.
- Países siempre visible sobre los puntos; el resto de capas auxiliares, bajo ellos.
- Coloreado por categoría o rango, iconos personalizables, tooltips y popups configurables.
- Filtros tipo panel de control (selección múltiple con búsqueda y rango de fechas) dentro del propio mapa.
- Título, subtítulo y logo opcionales; descarga del mapa y vista previa en la aplicación.

## Última evolución

- Las capas auxiliares dejan de ser fijas: ahora aparecen en el control de capas y el usuario decide cuáles arrancan activas.
- Leyenda unificada bajo «Capas geográficas auxiliares».
- La capa Países se muestra por encima de los puntos.

## Arquitectura y operación

- Aplicación Python con interfaz web local (Streamlit) y motor de generación basado en Folium/Leaflet.
- Los datos se procesan en el equipo del usuario; no se envían a servicios externos. El mapa generado carga las teselas
  base desde servidores públicos de Esri (y OpenStreetMap si se selecciona), por lo que requiere conexión para verse el fondo.
- Las capas corporativas se leen de una carpeta de red configurable.

## Limitaciones y dependencias

- Requiere acceso a la carpeta GIS corporativa para las capas auxiliares; sin ella, se omiten con un aviso.
- Mapas con muchos puntos pueden pesar y tardar en abrirse; la vista previa en la aplicación es opcional por encima de cierto tamaño.
- Pendiente de formalizar: empaquetado/instalación, `requirements.txt` con versiones fijadas y pruebas automáticas.
