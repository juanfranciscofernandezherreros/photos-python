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
- La librería `rich` (barras de progreso). Instálala con:
  ```cmd
  pip install -r requirements.txt
  ```
- Una app de servidor WebDAV en el teléfono (por ejemplo, "WebDAV Server" en Play Store) que exponga el almacenamiento del móvil en una IP y puerto de tu red local
- Teléfono y PC conectados a la misma red Wi-Fi

## ⚙️ Configuración inicial

Todas las rutas del proyecto viven en `config.py`. Antes de la primera ejecución, revisa y ajusta:

```python
UNIDAD_WEBDAV = "Z:"                  # Letra de unidad que usarás en net use
CARPETA_BASE_PC = Path(r"C:\Develop") # Dónde quieres que se guarden tus fotos organizadas
```

Si tu teléfono guarda las capturas en una ruta distinta a `Pictures\Screenshots` o `DCIM\Screenshots`, añádela a `RUTAS_SCREENSHOTS_ORIGEN` en ese mismo archivo.

## ▶️ Uso paso a paso

1. **Abre la app WebDAV en tu teléfono** y anota la IP y puerto que muestra (ej. `192.168.1.133:8080`).

2. **Monta la unidad de red en Windows** (PowerShell o CMD):
   ```cmd
   net use Z: http://192.168.1.133:8080
   ```
   Comprueba que aparece una unidad `Z:` nueva en "Este equipo".

3. **Ejecuta el orquestador** desde la carpeta del proyecto:
   ```cmd
   python orchestador.py
   ```

4. En el menú, elige **T** para ejecutar todo el pipeline en orden, o el número de un paso concreto (por ejemplo `1` para solo descargar metadatos). Los tres pasos son:
   - **1 — Descargar**: escanea `Z:` y genera `metadatos_screenshots.json`
   - **2 — Organizar por fecha**: copia las capturas listadas en el JSON directamente desde `Z:` a `C:\Develop\screenshots_agrupados\AAAA\MM\DD`
   - **3 — Comprimir**: genera un `.zip` por cada carpeta de día

5. Cuando termines, puedes desmontar la unidad de red (opcional):
   ```cmd
   net use Z: /delete
   ```

## 🤖 Uso desatendido (CLI y Programador de tareas)

Además del menú interactivo, `orchestador.py` acepta argumentos de línea de comandos, pensados para lanzarlo sin intervención manual:

```cmd
python orchestador.py --todo          # Ejecuta los 3 pasos en orden
python orchestador.py --pasos 1,3     # Ejecuta solo los pasos indicados
```

Cada ejecución queda registrada en `orquestador.log` (junto a los scripts), con fecha y hora de cada paso. Útil para revisar qué pasó tras una ejecución nocturna sin tener que estar delante de la pantalla.

El proceso termina con código de salida `0` si todo fue bien o `1` si algo falló, así que puedes programarlo con el **Programador de tareas de Windows**:

1. Crea una tarea nueva → Acción: "Iniciar un programa"
2. Programa: la ruta a tu `python.exe`
3. Argumentos: `orchestador.py --todo`
4. Iniciar en: la carpeta del proyecto (donde está `orchestador.py`)

Antes de esto necesitas que la unidad `Z:` ya esté montada (paso 2 de arriba) — el Programador de tareas no la monta por ti.

## 📁 Estructura del proyecto

```
photos-python/
├── config.py                    # Rutas y constantes centralizadas
├── requirements.txt              # Dependencias (rich, para las barras de progreso)
├── 01_descargar_archivos.py     # Z: -> metadatos_screenshots.json
├── 02_organizar_por_fecha.py    # JSON -> screenshots_agrupados\AAAA\MM\DD (copia única)
├── 03_comprimir.py              # screenshots_agrupados -> .zip por día
├── orchestador.py                # Menú interactivo para ejecutar los pasos anteriores
└── metadatos_screenshots.json   # Generado automáticamente, no se sube al repo
```