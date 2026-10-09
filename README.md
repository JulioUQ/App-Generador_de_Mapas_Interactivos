# Generador de Mapas Interactivos

Aplicación para la generación y visualización de mapas interactivos a partir de capas y datos geoespaciales.

## Requisitos

* Python 3.10 o superior
* Windows
* Acceso a las capas GIS necesarias para la aplicación

## Instalación y ejecución

La forma más sencilla de iniciar la aplicación es ejecutar:

```text
iniciar_mapas.bat
```

La primera ejecución prepara automáticamente el entorno virtual e instala las dependencias necesarias. Este proceso puede tardar unos minutos.

Una vez iniciado el sistema, se abrirá automáticamente el navegador con la aplicación.

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

```text
src/
├── app.py
├── mapas_core.py
├── generar_mapa_asistente.py
└── geo_functions.py
```

### Principales módulos

| Archivo                     | Función                                                  |
| --------------------------- | -------------------------------------------------------- |
| `app.py`                    | Interfaz principal de la aplicación                      |
| `mapas_core.py`             | Integración y coordinación de los diferentes componentes |
| `generar_mapa_asistente.py` | Motor de generación de mapas                             |
| `geo_functions.py`          | Funciones relacionadas con capas y operaciones GIS       |

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
