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
                 Se escanea la carpeta indicada en "ruta_remota".
    - "destino": al terminar de organizar localmente, el paso
                 `upload_ssh.py` sube la carpeta organizada a este servidor,
                 a la carpeta indicada en "ruta_remota" (o en
                 "ruta_remota_destino" si se ha indicado una distinta).
    - "ambos":   se usa a la vez como origen y como destino. En este caso
                 "ruta_remota" (origen a escanear) y "ruta_remota_destino"
                 (destino donde se sube lo organizado) DEBEN ser rutas
                 distintas: si coincidieran, cada ejecución del pipeline
                 volvería a encontrar como "origen" los propios ficheros
                 que subió la ejecución anterior, escaneando cada vez una
                 carpeta más profunda sin necesidad. anadir_o_actualizar_
                 conexion_ssh() rechaza guardar una conexión "ambos" sin
                 una ruta de destino distinta, precisamente para evitar
                 este bucle.

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

from .config import SSH_CONNECTIONS_JSON
from .json_io import read_json, write_json

try:
    import paramiko
except ImportError:
    paramiko = None

VALID_ROLES: list[str] = ["origen", "destino", "ambos"]
DEFAULT_SSH_PORT: int = 22


class SSHConnection(TypedDict):
    alias: str            # nombre libre para identificar el servidor, ej. "NAS de casa"
    host: str             # IP o dominio del servidor Linux
    puerto: int            # normalmente 22
    usuario: str
    ruta_remota: str       # carpeta remota de ORIGEN a escanear (y también de destino, si rol="destino" y no se indica ruta_remota_destino)
    ruta_remota_destino: str  # carpeta remota de DESTINO donde upload lo organizado; "" = usar "ruta_remota" (solo válido si el rol no es "ambos")
    clave_privada: str    # ruta a un fichero de clave privada (ej. ~/.ssh/id_rsa); "" si no se usa
    rol: str              # "origen" | "destino" | "ambos" (ver VALID_ROLES)


def paramiko_available() -> bool:
    return paramiko is not None


def _require_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError(
            "Missing library 'paramiko', required for SSH connections. "
            "Install it with: pip install paramiko"
        )


# --------------------------------------------------------------- persistencia --
def load_ssh_connections() -> list[SSHConnection]:
    """Todas las conexiones SSH guardadas (uno o varios servidores Linux)."""
    datos = read_json(SSH_CONNECTIONS_JSON, default=[])
    return datos if isinstance(datos, list) else []


def save_ssh_connections(conexiones: list[SSHConnection]) -> None:
    write_json(SSH_CONNECTIONS_JSON, conexiones)


def add_or_update_ssh_connection(
    alias: str, host: str, puerto: int, usuario: str,
    ruta_remota: str, clave_privada: str = "", rol: str = "origen",
    ruta_remota_destino: str = "",
) -> list[SSHConnection]:
    """Guarda (o actualiza si el alias ya existía) una conexión SSH y
    devuelve la lista completa actualizada. Nunca se guarda la contraseña
    en disco: si el usuario se autentica por contraseña en vez de clave,
    se le pedirá cada vez que se use la conexión.

    Si rol="ambos", ruta_remota_destino es OBLIGATORIA y debe ser distinta
    de ruta_remota (ver el porqué en la cabecera del módulo): se lanza un
    ValueError si no se cumple, para que quien llame (GUI o CLI) se lo
    muestre al usuario en vez de guardar una configuración que provocaría
    un bucle de reescaneo.
    """
    if rol not in VALID_ROLES:
        rol = "origen"

    ruta_remota = ruta_remota.rstrip('/') or ruta_remota
    ruta_remota_destino = ruta_remota_destino.strip().rstrip('/')

    if rol == "ambos":
        if not ruta_remota_destino:
            raise ValueError(
                "With role 'ambos' you must specify a 'remote destination path' "
                "different from the source path, otherwise the pipeline would "
                "re-scan the files it just uploaded as new sources."
            )
        if ruta_remota_destino == ruta_remota.rstrip('/'):
            raise ValueError(
                "The remote destination path cannot be the same as the source path "
                "when the role is 'ambos'. Use a different subfolder, e.g. "
                f"'{ruta_remota.rstrip('/')}_organized'."
            )

    conexiones = load_ssh_connections()
    nueva: SSHConnection = {
        "alias": alias,
        "host": host,
        "puerto": puerto or DEFAULT_SSH_PORT,
        "usuario": usuario,
        "ruta_remota": ruta_remota,
        "ruta_remota_destino": ruta_remota_destino,
        "clave_privada": clave_privada,
        "rol": rol,
    }
    conexiones = [c for c in conexiones if c["alias"] != alias]
    conexiones.append(nueva)
    save_ssh_connections(conexiones)
    return conexiones


def effective_destination_path(conexion_ssh: SSHConnection) -> str:
    """La carpeta remota donde upload lo organizado: 'ruta_remota_destino'
    si se ha indicado una, o si no 'ruta_remota' (comportamiento de
    siempre, válido para conexiones antiguas y para rol='destino' con una
    sola carpeta). Nunca devuelve "" si la conexión es válida."""
    return conexion_ssh.get("ruta_remota_destino") or conexion_ssh["ruta_remota"]


def remove_ssh_connection(alias: str) -> list[SSHConnection]:
    conexiones = [c for c in load_ssh_connections() if c["alias"] != alias]
    save_ssh_connections(conexiones)
    return conexiones


def get_connection(alias: str) -> Optional[SSHConnection]:
    for c in load_ssh_connections():
        if c["alias"] == alias:
            return c
    return None


def connections_by_role(rol_deseado: str) -> list[SSHConnection]:
    """Connectiones cuyo rol coincide, incluyendo las de rol 'ambos'."""
    return [
        c for c in load_ssh_connections()
        if c.get("rol") == rol_deseado or c.get("rol") == "ambos"
    ]


# --------------------------------------------------------------- cliente SFTP --
class SSHClient:
    """Envuelve una conexión SSH/SFTP abierta a un servidor Linux.

    Uso recomendado como gestor de contexto:
        with SSHClient(conexion) as cliente:
            cliente.list_files_recursive(...)
    """

    def __init__(self, conexion: SSHConnection, contrasena: str = "") -> None:
        _require_paramiko()
        self.conexion = conexion
        self._contrasena = contrasena
        self._ssh: Any = None
        self._sftp: Any = None

    def __enter__(self) -> "SSHClient":
        self.connect()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def connect(self) -> None:
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict[str, Any] = dict(
            hostname=self.conexion["host"],
            port=int(self.conexion.get("puerto") or DEFAULT_SSH_PORT),
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

    def close(self) -> None:
        try:
            if self._sftp is not None:
                self._sftp.close()
        finally:
            if self._ssh is not None:
                self._ssh.close()

    def test_connection(self) -> tuple[bool, str]:
        """Igual que connection.mount()/unmount(): nunca lanza una
        excepción, la traduce a (éxito, mensaje) para mostrarla tal cual en
        la ventana o en el log de la CLI."""
        etiqueta = f"{self.conexion['usuario']}@{self.conexion['host']}:{self.conexion.get('puerto', 22)}"
        try:
            self.connect()
            ruta = self.conexion["ruta_remota"]
            self._sftp.listdir(ruta)
            return True, f"✅ Connection successful to {etiqueta} — '{ruta}' is accessible."
        except Exception as e:
            return False, f"❌ Could not connect to {etiqueta} or read '{self.conexion['ruta_remota']}': {e}"
        finally:
            self.close()

    def list_files_recursive(self, ruta_remota: str, extensiones_validas: list[str]) -> list[dict[str, Any]]:
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
                encontrados.extend(self.list_files_recursive(ruta_completa, extensiones_validas))
            elif PurePosixPath(ruta_completa).suffix.lower() in extensiones_validas:
                encontrados.append({
                    "ruta": ruta_completa,
                    "tamano": entrada.st_size,
                    "mtime": entrada.st_mtime,
                })
        return encontrados

    def download(self, ruta_remota: str, ruta_local: Path) -> None:
        """Trae un fichero del servidor Linux al PC (usado cuando el
        servidor es el ORIGEN)."""
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        self._sftp.get(ruta_remota, str(ruta_local))

    def upload(self, ruta_local: Path, ruta_remota: str) -> None:
        """Envía un fichero del PC al servidor Linux (usado cuando el
        servidor es el DESTINO), creando las carpetas remotas necesarias."""
        self._create_remote_directories(str(PurePosixPath(ruta_remota).parent))
        self._sftp.put(str(ruta_local), ruta_remota)

    def remote_exists(self, ruta_remota: str) -> Optional[int]:
        """Devuelve el tamaño en bytes si el fichero remoto ya existe, o
        None si no existe. Se usa para no volver a upload/download lo que
        ya está transferido (idempotencia, igual que hace organizar.py con
        `destino_final.exists()`)."""
        try:
            return self._sftp.stat(ruta_remota).st_size
        except FileNotFoundError:
            return None

    def _create_remote_directories(self, ruta_remota: str) -> None:
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
