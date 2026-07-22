import json
import uuid
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from rich.progress import track

from .carpetas import cargar_carpetas_guardadas
from .config import ARCHIVO_METADATOS_JSON, EXTENSIONES_VALIDAS
from . import conexion, ssh_conexion

MetadatosCaptura = dict[str, Any]


def cargar_metadatos_existentes() -> dict[str, MetadatosCaptura]:
    archivo = Path(ARCHIVO_METADATOS_JSON)
    if not archivo.exists():
        return {}
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            lista_previa: list[MetadatosCaptura] = json.load(f)
        return {item["ruta_original"]: item for item in lista_previa}
    except (json.JSONDecodeError, KeyError):
        print(f"⚠️ Existing '{ARCHIVO_METADATOS_JSON}' is corrupt, it will be regenerated from scratch.\n")
        return {}


def obtener_fecha_real(nombre_archivo: str, mtime_fallback: float) -> str:
    """
    Intenta extraer la fecha exacta desde el nombre del archivo (Screenshot_20231024_153020).
    Es la forma más fiable porque WebDAV a menudo rompe las fechas del sistema de archivos.
    """
    # Busca Año, Mes, Día y Hora, Minuto, Segundo separados por cualquier cosa
    match_completo = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})\D*(\d{2})', nombre_archivo)
    if match_completo:
        a, m, d, h, mn, s = match_completo.groups()
        # Validamos que los números tengan sentido como fechas
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31 and 0 <= int(h) <= 23:
            return f"{a}-{m}-{d} {h}:{mn}:{s}"
            
    # Si no tiene hora, buscamos solo la fecha (Año, Mes, Día)
    match_fecha = re.search(r'(20\d{2})\D*(\d{2})\D*(\d{2})', nombre_archivo)
    if match_fecha:
        a, m, d = match_fecha.groups()
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{a}-{m}-{d} 12:00:00"
            
    # Fallback: Si el nombre no tiene fecha, confiamos en lo que diga el disco
    return datetime.fromtimestamp(mtime_fallback).strftime('%Y-%m-%d %H:%M:%S')


def escanear_servidor_ssh(conexion_ssh: ssh_conexion.ConexionSSH) -> list[dict[str, Any]]:
    """Se conecta por SFTP a un servidor Linux configurado como origen (o
    'ambos') y devuelve una lista de "candidatos" con la misma forma que
    los ficheros locales, pero marcados con ssh_alias/ssh_ruta_remota para
    que organizar.py sepa que hay que descargarlos por SFTP en vez de
    copiarlos con shutil."""
    alias = conexion_ssh["alias"]
    ruta_remota = conexion_ssh["ruta_remota"]

    try:
        with ssh_conexion.ClienteSSH(conexion_ssh) as cliente:
            archivos = cliente.listar_archivos_recursivo(ruta_remota, EXTENSIONES_VALIDAS)
    except Exception as e:
        print(f"⚠️ No se pudo escanear el servidor SSH '{alias}' ({conexion_ssh['host']}): {e}")
        return []

    candidatos = []
    for archivo in archivos:
        nombre = PurePosixPath(archivo["ruta"]).name
        candidatos.append({
            "ruta_str": f"ssh://{alias}{archivo['ruta']}",
            "archivo": nombre,
            "formato": PurePosixPath(nombre).suffix.lower().replace('.', ''),
            "tamano_mb": round(archivo["tamano"] / (1024 * 1024), 2),
            "mtime": archivo["mtime"],
            "ssh_alias": alias,
            "ssh_ruta_remota": archivo["ruta"],
        })
    return candidatos


def exportar_metadatos_json() -> None:
    print("Searching for screenshots on connected drives and extracting metadata...\n")

    carpetas_a_escanear = cargar_carpetas_guardadas()
    servidores_ssh_origen = ssh_conexion.conexiones_por_rol("origen")

    if not carpetas_a_escanear and not servidores_ssh_origen:
        print("❌ No connection or folder configured yet. Use 'Conexión WebDAV' or "
              "'Conexión SSH' in the main window to connect a phone or a Linux server first.")
        return

    conexiones_guardadas = conexion.cargar_conexiones()
    if conexiones_guardadas:
        for c in conexiones_guardadas:
            estado = "✅ mounted" if conexion.esta_montada(c["letra"]) else "⚠️ NOT mounted right now"
            print(f"  {c['letra']} ({c.get('alias', c['letra'])} — {c.get('ip')}:{c.get('puerto')}): {estado}")
        print()

    archivos_encontrados: list[Path] = []
    errores_listado = 0

    for ruta in carpetas_a_escanear:
        if not (ruta.exists() and ruta.is_dir()):
            print(f"⚠️ Subfolder not found on drive: {ruta}")
            continue

        print(f"✅ Extracting data from: {ruta}")
        try:
            for candidato in ruta.rglob('*'):
                try:
                    if candidato.is_file() and candidato.suffix.lower() in EXTENSIONES_VALIDAS:
                        archivos_encontrados.append(candidato)
                except OSError as e:
                    errores_listado += 1
        except OSError as e:
            errores_listado += 1

    # --- Servidores Linux por SSH configurados como origen ---
    candidatos_ssh: list[dict[str, Any]] = []
    if servidores_ssh_origen:
        if not ssh_conexion.paramiko_disponible():
            print("⚠️ Hay servidores SSH configurados como origen, pero falta 'paramiko'. "
                  "Instálalo con: pip install paramiko\n")
        else:
            for c in servidores_ssh_origen:
                print(f"✅ Extracting data from SSH server: {c['alias']} "
                      f"({c['usuario']}@{c['host']}:{c['ruta_remota']})")
                candidatos_ssh.extend(escanear_servidor_ssh(c))
            print()

    metadatos_previos = cargar_metadatos_existentes()
    metadatos_actuales = {}
    nuevos = 0
    sin_cambios = 0

    for archivo in track(archivos_encontrados, description="Analyzing screenshots..."):
        ruta_str = str(archivo)

        try:
            stats = archivo.stat()
            peso_mb = round(stats.st_size / (1024 * 1024), 2)
            anterior = metadatos_previos.get(ruta_str)

            if (anterior
                    and anterior.get("tamano_mb") == peso_mb
                    and anterior.get("mtime") == stats.st_mtime):
                if "id" not in anterior:
                    anterior["id"] = str(uuid.uuid4())
                metadatos_actuales[ruta_str] = anterior
                sin_cambios += 1
                continue

            # --- MAGIA AQUÍ: Sacamos la fecha real del nombre ---
            fecha_legible = obtener_fecha_real(archivo.name, stats.st_mtime)

            id_captura = anterior["id"] if anterior and "id" in anterior else str(uuid.uuid4())

            metadatos_actuales[ruta_str] = {
                "id": id_captura,
                "archivo": archivo.name,
                "formato": archivo.suffix.lower().replace('.', ''),
                "tamano_mb": peso_mb,
                "mtime": stats.st_mtime,
                "fecha_captura": fecha_legible,
                "ruta_original": ruta_str
            }
            nuevos += 1

        except OSError:
            continue

    for candidato in track(candidatos_ssh, description="Analyzing screenshots on SSH servers..."):
        ruta_str = candidato["ruta_str"]
        peso_mb = candidato["tamano_mb"]
        anterior = metadatos_previos.get(ruta_str)

        if (anterior
                and anterior.get("tamano_mb") == peso_mb
                and anterior.get("mtime") == candidato["mtime"]):
            if "id" not in anterior:
                anterior["id"] = str(uuid.uuid4())
            metadatos_actuales[ruta_str] = anterior
            sin_cambios += 1
            continue

        fecha_legible = obtener_fecha_real(candidato["archivo"], candidato["mtime"])
        id_captura = anterior["id"] if anterior and "id" in anterior else str(uuid.uuid4())

        metadatos_actuales[ruta_str] = {
            "id": id_captura,
            "archivo": candidato["archivo"],
            "formato": candidato["formato"],
            "tamano_mb": peso_mb,
            "mtime": candidato["mtime"],
            "fecha_captura": fecha_legible,
            "ruta_original": ruta_str,
            "ssh_alias": candidato["ssh_alias"],
            "ssh_ruta_remota": candidato["ssh_ruta_remota"],
        }
        nuevos += 1

    eliminados = len(metadatos_previos) - sum(1 for r in metadatos_previos if r in metadatos_actuales)
    lista_metadatos = list(metadatos_actuales.values())

    if len(lista_metadatos) > 0:
        with open(ARCHIVO_METADATOS_JSON, 'w', encoding='utf-8') as f:
            json.dump(lista_metadatos, f, indent=4, ensure_ascii=False)
        print("-" * 50)
        print(f"✅ Success! Metadata extracted and dates corrected.")
    else:
        print("❌ No screenshots found to export.")

if __name__ == "__main__":
    exportar_metadatos_json()