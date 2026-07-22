"""
Gestión de conexiones SSH/SFTP a servidores Linux.

Complementa a conexion.py (WebDAV para móviles): mientras que conexion.py
monta el móvil como una unidad de red con letra (Z:, Y:...) usando el
comando nativo de Windows `net use`, este módulo NO monta nada — habla
directamente por SFTP (sobre SSH) con un servidor Linux, así que funciona
igual en Windows, Linux o macOS sin drivers ni letras de unidad.

Cada conexión guardada representa un servidor Linux, y tiene un "rol":
    - "origen":  el pipeline TAMBIÉN escanea este servidor en busca de
                 capturas, igual que hace con las carpetas de un móvil.
    - "destino": al terminar de organizar localmente, el paso
                 `subir_ssh.py` sube la carpeta organizada a este servidor.
    - "ambos":   se usa a la vez como origen y como destino.

Deliberadamente sin ningún import de PyQt6, igual que conexion.py y
carpetas.py: así el modo desatendido (`photos-sync --todo`) puede usar una
conexión SSH ya guardada sin necesitar cargar la interfaz gráfica.

Requiere la librería 'paramiko' (pip install paramiko). Si no está
instalada, todas las funciones que sí dependen de ella lo indican con un
mensaje claro en vez de fallar con un ImportError críptico.
"""
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any, Optional, TypedDict

from .config import ARCHIVO_CONEXIONES_SSH_JSON

try:
    import paramiko
except ImportError:
    paramiko = None

ROLES_VALIDOS: list[str] = ["origen", "destino", "ambos"]
PUERTO_SSH_POR_DEFECTO: int = 22


class ConexionSSH(TypedDict):
    alias: str            # nombre libre para identificar el servidor, ej. "NAS de casa"
    host: str             # IP o dominio del servidor Linux
    puerto: int            # normalmente 22
    usuario: str
    ruta_remota: str       # carpeta remota: origen a escanear y/o destino a recibir archivos
    clave_privada: str    # ruta a un fichero de clave privada (ej. ~/.ssh/id_rsa); "" si no se usa
    rol: str              # "origen" | "destino" | "ambos" (ver ROLES_VALIDOS)


def paramiko_disponible() -> bool:
    return paramiko is not None


def _requiere_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError(
            "Falta la librería 'paramiko', necesaria para las conexiones SSH. "
            "Instálala con: pip install paramiko"
        )


# --------------------------------------------------------------- persistencia --
def cargar_conexiones_ssh() -> list[ConexionSSH]:
    """Todas las conexiones SSH guardadas (uno o varios servidores Linux)."""
    archivo = Path(ARCHIVO_CONEXIONES_SSH_JSON)
    if not archivo.exists():
        return []
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        return datos if isinstance(datos, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def guardar_conexiones_ssh(conexiones: list[ConexionSSH]) -> None:
    with open(ARCHIVO_CONEXIONES_SSH_JSON, 'w', encoding='utf-8') as f:
        json.dump(conexiones, f, indent=4, ensure_ascii=False)


def anadir_o_actualizar_conexion_ssh(
    alias: str, host: str, puerto: int, usuario: str,
    ruta_remota: str, clave_privada: str = "", rol: str = "origen",
) -> list[ConexionSSH]:
    """Guarda (o actualiza si el alias ya existía) una conexión SSH y
    devuelve la lista completa actualizada. Nunca se guarda la contraseña
    en disco: si el usuario se autentica por contraseña en vez de clave,
    se le pedirá cada vez que se use la conexión."""
    if rol not in ROLES_VALIDOS:
        rol = "origen"

    conexiones = cargar_conexiones_ssh()
    nueva: ConexionSSH = {
        "alias": alias,
        "host": host,
        "puerto": puerto or PUERTO_SSH_POR_DEFECTO,
        "usuario": usuario,
        "ruta_remota": ruta_remota,
        "clave_privada": clave_privada,
        "rol": rol,
    }
    conexiones = [c for c in conexiones if c["alias"] != alias]
    conexiones.append(nueva)
    guardar_conexiones_ssh(conexiones)
    return conexiones


def quitar_conexion_ssh(alias: str) -> list[ConexionSSH]:
    conexiones = [c for c in cargar_conexiones_ssh() if c["alias"] != alias]
    guardar_conexiones_ssh(conexiones)
    return conexiones


def obtener_conexion(alias: str) -> Optional[ConexionSSH]:
    for c in cargar_conexiones_ssh():
        if c["alias"] == alias:
            return c
    return None


def conexiones_por_rol(rol_deseado: str) -> list[ConexionSSH]:
    """Conexiones cuyo rol coincide, incluyendo las de rol 'ambos'."""
    return [
        c for c in cargar_conexiones_ssh()
        if c.get("rol") == rol_deseado or c.get("rol") == "ambos"
    ]


# --------------------------------------------------------------- cliente SFTP --
class ClienteSSH:
    """Envuelve una conexión SSH/SFTP abierta a un servidor Linux.

    Uso recomendado como gestor de contexto:
        with ClienteSSH(conexion) as cliente:
            cliente.listar_archivos_recursivo(...)
    """

    def __init__(self, conexion: ConexionSSH, contrasena: str = "") -> None:
        _requiere_paramiko()
        self.conexion = conexion
        self._contrasena = contrasena
        self._ssh: Any = None
        self._sftp: Any = None

    def __enter__(self) -> "ClienteSSH":
        self.conectar()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.cerrar()

    def conectar(self) -> None:
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict[str, Any] = dict(
            hostname=self.conexion["host"],
            port=int(self.conexion.get("puerto") or PUERTO_SSH_POR_DEFECTO),
            username=self.conexion["usuario"],
            timeout=15,
        )

        clave = self.conexion.get("clave_privada")
        if clave:
            kwargs["key_filename"] = str(Path(clave).expanduser())
        elif self._contrasena:
            kwargs["password"] = self._contrasena
        else:
            # Sin clave ni contraseña explícitas: probamos el agente SSH y
            # las claves por defecto del usuario (~/.ssh/id_rsa, etc.)
            kwargs["allow_agent"] = True
            kwargs["look_for_keys"] = True

        self._ssh.connect(**kwargs)
        self._sftp = self._ssh.open_sftp()

    def cerrar(self) -> None:
        try:
            if self._sftp is not None:
                self._sftp.close()
        finally:
            if self._ssh is not None:
                self._ssh.close()

    def probar(self) -> tuple[bool, str]:
        """Igual que conexion.montar()/desmontar(): nunca lanza una
        excepción, la traduce a (éxito, mensaje) para mostrarla tal cual en
        la ventana o en el log de la CLI."""
        etiqueta = f"{self.conexion['usuario']}@{self.conexion['host']}:{self.conexion.get('puerto', 22)}"
        try:
            self.conectar()
            ruta = self.conexion["ruta_remota"]
            self._sftp.listdir(ruta)
            return True, f"✅ Conexión correcta con {etiqueta} — '{ruta}' es accesible."
        except Exception as e:
            return False, f"❌ No se pudo conectar a {etiqueta} o leer '{self.conexion['ruta_remota']}': {e}"
        finally:
            self.cerrar()

    def listar_archivos_recursivo(self, ruta_remota: str, extensiones_validas: list[str]) -> list[dict[str, Any]]:
        """Recorre `ruta_remota` (y subcarpetas) por SFTP y devuelve una
        lista de dicts {ruta, tamano, mtime} por cada fichero cuya
        extensión esté en `extensiones_validas`. Se hace en un solo barrido
        recursivo para minimizar las idas y vueltas por la red."""
        encontrados: list[dict[str, Any]] = []
        try:
            entradas = self._sftp.listdir_attr(ruta_remota)
        except FileNotFoundError:
            return encontrados

        for entrada in entradas:
            ruta_completa = str(PurePosixPath(ruta_remota) / entrada.filename)
            if stat.S_ISDIR(entrada.st_mode):
                encontrados.extend(self.listar_archivos_recursivo(ruta_completa, extensiones_validas))
            elif PurePosixPath(ruta_completa).suffix.lower() in extensiones_validas:
                encontrados.append({
                    "ruta": ruta_completa,
                    "tamano": entrada.st_size,
                    "mtime": entrada.st_mtime,
                })
        return encontrados

    def descargar(self, ruta_remota: str, ruta_local: Path) -> None:
        """Trae un fichero del servidor Linux al PC (usado cuando el
        servidor es el ORIGEN)."""
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        self._sftp.get(ruta_remota, str(ruta_local))

    def subir(self, ruta_local: Path, ruta_remota: str) -> None:
        """Envía un fichero del PC al servidor Linux (usado cuando el
        servidor es el DESTINO), creando las carpetas remotas necesarias."""
        self._crear_directorios_remotos(str(PurePosixPath(ruta_remota).parent))
        self._sftp.put(str(ruta_local), ruta_remota)

    def existe_remoto(self, ruta_remota: str) -> Optional[int]:
        """Devuelve el tamaño en bytes si el fichero remoto ya existe, o
        None si no existe. Se usa para no volver a subir/descargar lo que
        ya está transferido (idempotencia, igual que hace organizar.py con
        `destino_final.exists()`)."""
        try:
            return self._sftp.stat(ruta_remota).st_size
        except FileNotFoundError:
            return None

    def _crear_directorios_remotos(self, ruta_remota: str) -> None:
        """Equivalente a `mkdir -p` en remoto: SFTP no lo hace de forma
        nativa, hay que crear cada nivel de carpeta uno a uno."""
        partes = [p for p in PurePosixPath(ruta_remota).parts if p != "/"]
        actual = ""
        for parte in partes:
            actual += f"/{parte}"
            try:
                self._sftp.stat(actual)
            except FileNotFoundError:
                self._sftp.mkdir(actual)
