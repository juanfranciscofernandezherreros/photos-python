"""
Ventana gráfica para elegir qué carpetas del teléfono (montado como unidad
de red) se escanean en busca de capturas de pantalla.

La selección se guarda en un JSON en la carpeta de trabajo actual (el cwd),
no dentro del paquete instalado — así puedes tener distintas selecciones
en distintas carpetas de trabajo sin tocar el código fuente.

Ejecútalo con:
    photos-sync-carpetas
o desde el menú interactivo de `photos-sync` (opción C).
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .carpetas import cargar_carpetas_guardadas, guardar_carpetas
from .config import ARCHIVO_CARPETAS_SELECCIONADAS, UNIDAD_WEBDAV


class SelectorCarpetas(tk.Tk):
    """Ventana principal: lista las carpetas elegidas y permite añadir o
    quitar mediante el explorador de archivos nativo de Windows."""

    def __init__(self) -> None:
        super().__init__()
        self.title("photos-sync — Selección de carpetas")
        self.geometry("560x360")
        self.resizable(False, False)

        self.carpetas: list[Path] = cargar_carpetas_guardadas()

        tk.Label(
            self,
            text="Carpetas del teléfono donde buscar capturas de pantalla:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        marco_lista = tk.Frame(self)
        marco_lista.pack(fill="both", expand=True, padx=12)

        self.lista = tk.Listbox(marco_lista, font=("Consolas", 9), selectmode=tk.SINGLE)
        self.lista.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(marco_lista, orient="vertical", command=self.lista.yview)
        scrollbar.pack(side="right", fill="y")
        self.lista.config(yscrollcommand=scrollbar.set)

        self._refrescar_lista()

        marco_botones = tk.Frame(self)
        marco_botones.pack(fill="x", padx=12, pady=12)

        tk.Button(marco_botones, text="➕ Añadir carpeta...", command=self._anadir_carpeta).pack(side="left")
        tk.Button(marco_botones, text="➖ Quitar seleccionada", command=self._quitar_carpeta).pack(side="left", padx=8)
        tk.Button(marco_botones, text="💾 Guardar y cerrar", command=self._guardar_y_cerrar).pack(side="right")
        tk.Button(marco_botones, text="Cancelar", command=self.destroy).pack(side="right", padx=8)

    def _refrescar_lista(self) -> None:
        self.lista.delete(0, tk.END)
        for carpeta in self.carpetas:
            self.lista.insert(tk.END, str(carpeta))

    def _anadir_carpeta(self) -> None:
        # Arrancamos el explorador en la unidad de red configurada (ej. Z:\),
        # así se navega directamente por el teléfono en vez de por el PC.
        carpeta_z = Path(f"{UNIDAD_WEBDAV}\\")
        inicio = str(carpeta_z) if carpeta_z.exists() else str(Path.home())

        carpeta = filedialog.askdirectory(
            title="Elige una carpeta del teléfono", initialdir=inicio, parent=self
        )
        if not carpeta:
            return

        ruta = Path(carpeta)
        if ruta in self.carpetas:
            messagebox.showinfo("Ya está en la lista", f"'{ruta}' ya estaba seleccionada.", parent=self)
            return

        self.carpetas.append(ruta)
        self._refrescar_lista()

    def _quitar_carpeta(self) -> None:
        seleccion = self.lista.curselection()
        if not seleccion:
            messagebox.showinfo(
                "Nada seleccionado", "Elige primero una carpeta de la lista para quitarla.", parent=self
            )
            return

        del self.carpetas[seleccion[0]]
        self._refrescar_lista()

    def _guardar_y_cerrar(self) -> None:
        if not self.carpetas:
            continuar = messagebox.askyesno(
                "Sin carpetas seleccionadas",
                "No has seleccionado ninguna carpeta, así que el pipeline no "
                "encontrará capturas.\n¿Guardar igualmente?",
                parent=self,
            )
            if not continuar:
                return

        guardar_carpetas(self.carpetas)
        messagebox.showinfo("Guardado", f"Selección guardada en '{ARCHIVO_CARPETAS_SELECCIONADAS}'.", parent=self)
        self.destroy()


def main() -> None:
    """Punto de entrada del comando `photos-sync-carpetas` (ver pyproject.toml)."""
    app = SelectorCarpetas()
    app.mainloop()


if __name__ == "__main__":
    main()
