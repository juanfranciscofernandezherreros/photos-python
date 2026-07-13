# 📱 Nothing Phone Sync: WebDAV & Python Automation

Este proyecto es un ecosistema de scripts en Python diseñado para automatizar la extracción, organización y compresión de capturas de pantalla (screenshots) desde un Nothing Phone (o cualquier dispositivo Android) hacia un PC con Windows 11.

## 🚀 El Problema que Resuelve

Por defecto, Windows conecta los teléfonos Android mediante el protocolo **MTP (Media Transfer Protocol)**. Esto monta el dispositivo como un "reproductor multimedia" sin asignarle una letra de unidad física (como `C:\` o `Z:\`). Debido a esto, los lenguajes de programación como Python no pueden leer los archivos del móvil de forma nativa utilizando rutas estándar.

**La Solución:** En lugar de utilizar cables USB o lidiar con ADB y problemas de drivers, este proyecto utiliza **WebDAV a través de Wi-Fi** para engañar a Windows y montar el almacenamiento del teléfono como si fuera un disco duro en red.

---

## 🔑 La Magia del Comando: `net use`

El pilar de este proyecto es el siguiente comando ejecutado en la terminal de Windows:

```cmd
net use Z: http://192.168.1.133:8080
```

Qué hace exactamente este comando?

net use: Es la herramienta nativa de Windows para conectarse a carpetas compartidas y servidores en una red local.

Z:: Le ordena a Windows que tome esa conexión de red y la disfrace creando un "disco duro virtual" visible en Este equipo con la letra Z.

http://192.168.1.133:8080: Es la dirección IP local y el puerto donde el Nothing Phone está transmitiendo sus archivos mediante una aplicación de servidor WebDAV.

Al ejecutar esto, el móvil deja de ser un "dispositivo virtual" y pasa a ser la unidad Z:\. A partir de este momento, Python puede leer, copiar y modificar los archivos del teléfono a máxima velocidad utilizando la librería estándar pathlib.

---

## 🧰 Requisitos

- Windows 11 (o cualquier Windows con soporte para `net use`)
- Python 3.9 o superior
- Una app de servidor WebDAV en el teléfono (por ejemplo, "WebDAV Server" en Play Store) que exponga el almacenamiento del móvil en una IP y puerto de tu red local
- Teléfono y PC conectados a la misma red Wi-Fi

## 📦 Instalación

El proyecto es un paquete instalable. Desde la carpeta raíz del repositorio (donde está `pyproject.toml`):

```cmd
pip install -e .
```

Esto instala `rich` y `PyQt6` (las dos dependencias) y registra los comandos `photos-sync` y `photos-sync-gui` en tu terminal — puedes ejecutarlos desde cualquier carpeta a partir de ahora.

`-e` es instalación "editable": si luego modificas el código fuente, los cambios se aplican al momento sin tener que reinstalar.

## ⚙️ Configuración inicial

Ya no hace falta editar ningún archivo a mano. `photos_sync/config.py` solo guarda rutas técnicas (dónde se guardan las fotos organizadas, nombres de archivos JSON, etc.):

```python
CARPETA_BASE_PC = Path(r"C:\Develop")  # Dónde quieres que se guarden tus fotos organizadas
```

La conexión con el móvil (IP, puerto y letra de unidad) se hace **desde la propia ventana**, en el panel "📡 Conexión WebDAV" — ver más abajo.

## 🖼️ Todo se maneja desde una ventana gráfica

Ya no hay menús de texto, ni que escribir números en la terminal, ni que ejecutar `net use` a mano en otra ventana: `photos-sync` (o `python app.py`) abre una única ventana con:

- **📡 Conexión WebDAV**: eliges la **letra de unidad** en un desplegable (D: a Z:, evitando las reservadas A/B/C), pones la **IP** y el **puerto** que muestra la app WebDAV del móvil, y un nombre opcional para identificarlo. Al pulsar **🔗 Conectar**, la app ejecuta por ti exactamente `net use LETRA: http://IP:PUERTO` — no hace falta abrir CMD. Puedes conectar **varios móviles a la vez**, cada uno en su propia letra; todos aparecen en la lista con su estado (🟢 conectado / 🔴 no disponible), y **🔌 Desconectar seleccionada** ejecuta el `net use /delete` correspondiente.
- **⚙️ Configurar carpetas de origen/destino**: el selector gráfico de siempre. Si no seleccionas nada aquí, el pipeline usa automáticamente `Pictures\Screenshots` y `DCIM\Screenshots` de **cada** móvil que hayas conectado arriba — ya no hay ninguna letra fija en el código.
- Un botón por cada paso del pipeline (Descargar, Organizar, Comprimir, Contar por día) y un botón **▶ Ejecutar TODO**.
- Un panel de **registro** integrado en la propia ventana: todo lo que antes se imprimía en la terminal aparece ahí, en vivo, mientras el proceso corre en segundo plano sin congelar la ventana.

## ▶️ Uso paso a paso

1. **Abre la app WebDAV en tu teléfono** y anota la IP y puerto que muestra (ej. `192.168.1.133:8080`). Si vas a sincronizar varios móviles, anota la IP y puerto de cada uno.

2. **Abre la aplicación** desde la carpeta donde quieras que se guarden `metadatos_screenshots.json` y el resto de archivos generados (tu "carpeta de trabajo" — puede ser cualquiera, no hace falta estar dentro del repositorio):
   ```cmd
   photos-sync
   ```
   (equivalente a `photos-sync-gui`, o `python app.py` si trabajas desde el propio repositorio)

3. En el panel **📡 Conexión WebDAV**, elige una letra libre (por ejemplo `Z:`), escribe la IP y el puerto del móvil y pulsa **🔗 Conectar**. Repite con otra letra (`Y:`, `X:`...) por cada móvil adicional.

4. Configura las carpetas de destino si aún no lo has hecho (o déjalo así, y usará las rutas por defecto de cada móvil conectado) y pulsa **▶ Ejecutar TODO**, o los botones de cada paso por separado si prefieres ir uno a uno:
   - **1 — Descargar**: escanea todos los móviles conectados y genera `metadatos_screenshots.json`
   - **2 — Organizar por fecha**: copia las capturas listadas en el JSON a `destino\AAAA\MM\DD`
   - **3 — Comprimir**: genera un `.zip` por cada carpeta de día
   - **4 — Contar por día**: genera `resumen_por_dia.json` con el nº de fotos por día

5. Cuando termines, selecciona el móvil en la lista y pulsa **🔌 Desconectar seleccionada** (opcional).

## 🤖 Uso desatendido (CLI y Programador de tareas)

Además de la ventana gráfica, `photos-sync` acepta argumentos de línea de comandos pensados para lanzarlo sin intervención manual y sin abrir ninguna ventana:

```cmd
photos-sync --todo          # Ejecuta los 4 pasos en orden
photos-sync --pasos 1,3     # Ejecuta solo los pasos indicados
```

Cada ejecución queda registrada en `orquestador.log` (en la carpeta desde la que ejecutes el comando), con fecha y hora de cada paso. Útil para revisar qué pasó tras una ejecución nocturna sin tener que estar delante de la pantalla.

El proceso termina con código de salida `0` si todo fue bien o `1` si algo falló, así que puedes programarlo con el **Programador de tareas de Windows**:

1. Crea una tarea nueva → Acción: "Iniciar un programa"
2. Programa: `photos-sync` (o la ruta completa al ejecutable si no está en el PATH del sistema)
3. Argumentos: `--todo`
4. Iniciar en: la carpeta de trabajo donde quieras que se guarden el JSON y el log

Antes de esto necesitas que la unidad `Z:` ya esté montada (paso 2 de arriba) — el Programador de tareas no la monta por ti.

## 📁 Estructura del proyecto

```
photos-python/
├── pyproject.toml               # Metadatos del paquete y dependencias (pip install -e .)
├── app.py                       # Punto de entrada directo de la GUI (python app.py)
├── README.md
├── .gitignore
└── photos_sync/                 # El paquete instalable
    ├── __init__.py
    ├── config.py                # Rutas y constantes centralizadas
    ├── conexion.py               # Conexiones WebDAV: letra + IP + puerto, net use (una o varias)
    ├── carpetas.py              # Lógica de selección de carpetas (sin PyQt6)
    ├── selector_carpetas.py     # Ventana de configuración: `photos-sync-carpetas`
    ├── main_window.py           # Ventana principal: `photos-sync-gui` (botones + log)
    ├── descargar.py             # Z: -> metadatos_screenshots.json
    ├── organizar.py             # JSON -> screenshots_agrupados\AAAA\MM\DD
    ├── comprimir.py             # screenshots_agrupados -> .zip por día
    ├── resumen.py                # JSON -> resumen_por_dia.json
    ├── mantener_despierto.py     # Evita que Windows suspenda el PC mientras corre el pipeline
    └── cli.py                   # Punto de entrada del comando `photos-sync` (GUI o --todo/--pasos)
```

Cada módulo también se puede ejecutar de forma independiente para pruebas puntuales:
```cmd
python -m photos_sync.descargar
```

Los archivos generados en tiempo de ejecución (`metadatos_screenshots.json`, `orquestador.log`) se crean en la carpeta desde la que ejecutes `photos-sync`, no dentro del paquete — no se suben al repositorio.