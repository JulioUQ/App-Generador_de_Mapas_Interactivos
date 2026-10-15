# Ejercicio práctico: tu primer mapa interactivo

**Duración:** 30-40 minutos · **Nivel:** sin conocimientos previos · **Resultado:** un mapa HTML con filtros, capas y leyenda, y un script `.py` para regenerarlo.

Vas a representar 150 capturas pesqueras **ficticias** en el Mediterráneo (sur de Mallorca y Cartagena) junto con dos zonas de protección también ficticias. Los datos están inventados y las posiciones son aproximadas: sirven para practicar, no para analizar nada real.

## Material

Dentro de la carpeta `ejercicio/`:

| Archivo | Qué es |
|---|---|
| `datos_ejercicio.xlsx` | Hoja «Capturas»: Fecha, Barco, Puerto, Especie, Arte, Captura_kg, Latitud, Longitud (150 filas). |
| `zonas_ejercicio.geojson` | Dos polígonos: una veda temporal y una reserva marina (columnas: nombre, tipo, sup_km2). |

Hay 3 filas del Excel sin coordenadas, a propósito. Verás cómo las trata la aplicación.

## Paso 0 · Abrir la aplicación

1. Doble clic en `scripts\Iniciar_Mapas.bat`.
2. La primera vez tarda unos minutos en preparar todo. Al terminar se abre el navegador con la aplicación. **No cierres la ventana negra** mientras la uses.

## Paso 1 · Pestaña ① Posiciones

1. En **Archivos de posiciones**, sube `datos_ejercicio.xlsx`.
2. Comprueba la vista previa de la tabla. En **¿Qué columnas tienen las coordenadas?** deben salir `Latitud`, `Longitud` y `Fecha`. Si no, corrígelas.
3. En **Colorear los puntos**, elige **Por categorías** y, como columna, `Especie`. Abre *Cambiar colores u ocultar categorías* y mira cuántos puntos tiene cada especie.
4. Pon el **Tamaño de los puntos** en 4.
5. En **Al pasar el ratón por un punto, mostrar…** deja solo `Barco`, `Especie` y `Captura_kg`. En **Al hacer clic en un punto, mostrar…** deja todas las columnas menos las coordenadas.
6. En **Filtros desplegables** añade `Barco` y `Puerto`. Deja marcado el filtro por rango de fechas sobre «Fecha».
7. Ponle un nombre al conjunto, por ejemplo «Capturas», y, si quieres, un emoji (🐟).

## Paso 2 · Pestaña ② Capas

1. **Capa propia.** Pulsa **📂 Elegir capas del disco…**, selecciona `zonas_ejercicio.geojson` y acepta. Si la ventana no aparece, puede estar detrás del navegador. También puedes arrastrar el archivo en *Otra forma: arrastrar o subir archivos*.
2. Colorea la capa **Por categorías** usando la columna `tipo`. Deja la opacidad del relleno en 0,3. Como tooltip pon `nombre`, y en el popup todas las columnas.
3. **Capas geográficas auxiliares** (solo si tienes acceso a la carpeta GIS corporativa en P:\Proyectos\CALCULO_CIERRES\CONTROL CALIDAD\TeoríaSIPE\Programacion\Directorio GIS con QGIS\GIS_2.0): marca **Países** y deja activada «Activa al abrir el mapa». Si quieres, marca también otra (por ejemplo ZEE) pero **desactiva** su casilla «Activa al abrir el mapa», para ver cómo arranca apagada.

## Paso 3 · Pestaña ③ Título y mapa

1. Escribe un título («Capturas de ejemplo») y un subtítulo («Ejercicio práctico»).
2. Pulsa **🗺️ Generar mapa**.
3. Abre *Resumen de filas dibujadas*. Debe indicar cuántas filas se han descartado y por qué.
4. Revisa la vista previa y pulsa **⬇️ Descargar mapa (HTML)**. Ábrelo con doble clic en el navegador.

## Paso 4 · Explorar el mapa

Con el mapa abierto, responde. Las soluciones están al final.

1. ¿Cuántas posiciones se dibujan y cuántas filas se descartaron?
2. Abre el control de capas (arriba a la derecha). ¿Qué capas aparecen? Apaga y enciende la capa de zonas.
3. Pasa el ratón por un punto y haz clic en otro. ¿Qué información ofrece cada uno?
4. En el filtro de fechas, selecciona solo **marzo de 2026**. ¿Cuántas posiciones quedan visibles?
5. Quita el filtro de fechas. Filtra `Puerto = Palma` y la especie **Gamba roja** (desmarcando las demás en la leyenda). ¿Cuántas posiciones quedan?
6. En la leyenda, ¿bajo qué subtítulo aparecen las capas auxiliares?

## Paso 5 · Reto: el script `.py`

1. De vuelta en la aplicación, pulsa **⬇️ Descargar script (.py) para regenerar este mapa**.
2. Crea una carpeta de trabajo, copia el script y crea junto a él una carpeta `datos` con `datos_ejercicio.xlsx` y `zonas_ejercicio.geojson`.
3. Ejecútalo desde una terminal: `python generar_Capturas_de_ejemplo.py` (el nombre depende de tu título). Debe generar el mismo mapa.
4. **Para nota:** abre el script, busca la sección `CONFIGURACIÓN (editable)`, cambia el título o el color de una capa y vuelve a ejecutarlo.

## Soluciones

| Pregunta | Respuesta |
|---|---|
| 1 | **147** posiciones dibujadas y **3** filas descartadas por coordenadas vacías. |
| 2 | Capturas (con sus especies), Zonas y, si las activaste, las capas auxiliares. |
| 3 | El tooltip muestra Barco, Especie y Captura_kg. El popup muestra todas las columnas elegidas. |
| 4 | **34** posiciones. |
| 5 | **18** posiciones. |
| 6 | «Capas geográficas auxiliares». |

Conteo por especie (paso 1): Salmonete 36, Gamba roja 35, Merluza 32, Calamar 25, Pulpo 19.

