import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from .carpetas import cargar_carpetas_guardadas, guardar_carpetas
from .config import ARCHIVO_CARPETAS_SELECCIONADAS, UNIDAD_WEBDAV


class SelectorCarpetas(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("photos-sync — Folder Selection")
        self.geometry("560x360")
        self.resizable(False, False)

        self.carpetas: list[Path] = cargar_carpetas_guardadas()

        tk.Label(
            self,
            text="Phone folders to scan for screenshots:",
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

        tk.Button(marco_botones, text="➕ Add folder...", command=self._anadir_carpeta).pack(side="left")
        tk.Button(marco_botones, text="➖ Remove selected", command=self._quitar_carpeta).pack(side="left", padx=8)
        tk.Button(marco_botones, text="💾 Save and close", command=self._guardar_y_cerrar).pack(side="right")
        tk.Button(marco_botones, text="Cancel", command=self.destroy).pack(side="right", padx=8)

    def _refrescar_lista(self) -> None:
        self.lista.delete(0, tk.END)
        for carpeta in self.carpetas:
            self.lista.insert(tk.END, str(carpeta))

    def _anadir_carpeta(self) -> None:
        carpeta_z = Path(f"{UNIDAD_WEBDAV}\\")
        inicio = str(carpeta_z) if carpeta_z.exists() else str(Path.home())

        carpeta = filedialog.askdirectory(
            title="Choose a phone folder", initialdir=inicio, parent=self
        )
        if not carpeta:
            return

        ruta = Path(carpeta)
        if ruta in self.carpetas:
            messagebox.showinfo("Already in list", f"'{ruta}' was already selected.", parent=self)
            return

        self.carpetas.append(ruta)
        self._refrescar_lista()

    def _quitar_carpeta(self) -> None:
        seleccion = self.lista.curselection()
        if not seleccion:
            messagebox.showinfo(
                "Nothing selected", "Please select a folder from the list to remove it first.", parent=self
            )
            return

        del self.carpetas[seleccion[0]]
        self._refrescar_lista()

    def _guardar_y_cerrar(self) -> None:
        if not self.carpetas:
            continuar = messagebox.askyesno(
                "No folders selected",
                "You have not selected any folders, so the pipeline will not "
                "find any screenshots.\nSave anyway?",
                parent=self,
            )
            if not continuar:
                return

        guardar_carpetas(self.carpetas)
        messagebox.showinfo("Saved", f"Selection saved to '{ARCHIVO_CARPETAS_SELECCIONADAS}'.", parent=self)
        self.destroy()


def main() -> None:
    app = SelectorCarpetas()
    app.mainloop()


if __name__ == "__main__":
    main()
