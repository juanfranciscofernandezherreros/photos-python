import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from tkinterdnd2 import TkinterDnD, DND_FILES

# Asumimos que tienes (o crearás) estas funciones en tus módulos actuales
from .carpetas import (
    cargar_carpetas_guardadas, 
    guardar_carpetas, 
    cargar_destino_guardado, 
    guardar_destino
)
from .config import ARCHIVO_CARPETAS_SELECCIONADAS, UNIDAD_WEBDAV


class SelectorCarpetas(TkinterDnD.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("photos-sync — Configuración de Rutas")
        self.geometry("600x450")
        self.resizable(False, False)

        # Estado de la aplicación
        self.carpetas_origen: list[Path] = cargar_carpetas_guardadas()
        destino_previo = cargar_destino_guardado()
        self.carpeta_destino: Path | None = Path(destino_previo) if destino_previo else None

        self._construir_interfaz()

    def _construir_interfaz(self) -> None:
        # --- SECCIÓN 1: DESTINO ---
        marco_destino = tk.LabelFrame(self, text=" 📥 Carpeta de Destino (PC) ", font=("Segoe UI", 9, "bold"))
        marco_destino.pack(fill="x", padx=12, pady=(12, 6))

        self.lbl_destino = tk.Label(
            marco_destino, 
            text=str(self.carpeta_destino) if self.carpeta_destino else "Ninguna carpeta seleccionada", 
            fg="blue" if self.carpeta_destino else "red"
        )
        self.lbl_destino.pack(side="left", padx=12, pady=8)

        tk.Button(marco_destino, text="Examinar...", command=self._seleccionar_destino).pack(side="right", padx=12, pady=8)

        # --- SECCIÓN 2: ORIGEN (Múltiples carpetas) ---
        marco_origen = tk.LabelFrame(self, text=" 📱 Carpetas de Origen a Escanear (Teléfono) ", font=("Segoe UI", 9, "bold"))
        marco_origen.pack(fill="both", expand=True, padx=12, pady=6)

        tk.Label(marco_origen, text="Arrastra carpetas aquí o usa los botones:").pack(anchor="w", padx=12, pady=(8, 0))

        marco_lista = tk.Frame(marco_origen)
        marco_lista.pack(fill="both", expand=True, padx=12, pady=8)

        self.lista = tk.Listbox(marco_lista, font=("Consolas", 9), selectmode=tk.SINGLE)
        self.lista.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(marco_lista, orient="vertical", command=self.lista.yview)
        scrollbar.pack(side="right", fill="y")
        self.lista.config(yscrollcommand=scrollbar.set)

        # Drag & Drop para la lista
        self.lista.drop_target_register(DND_FILES)
        self.lista.dnd_bind('<<Drop>>', self._soltar_carpetas)

        self._refrescar_lista()

        # Botones de la lista
        marco_botones_lista = tk.Frame(marco_origen)
        marco_botones_lista.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(marco_botones_lista, text="➕ Añadir manualmente...", command=self._anadir_carpetas).pack(side="left")
        tk.Button(marco_botones_lista, text="➖ Quitar seleccionada", command=self._quitar_carpeta).pack(side="left", padx=8)

        # --- SECCIÓN 3: ACCIONES PRINCIPALES ---
        marco_accion = tk.Frame(self)
        marco_accion.pack(fill="x", padx=12, pady=12)
        tk.Button(marco_accion, text="💾 Guardar Configuración", command=self._guardar_y_cerrar, height=2, bg="#d4edda").pack(side="right")
        tk.Button(marco_accion, text="Cancelar", command=self.destroy, height=2).pack(side="right", padx=8)

    # --- MÉTODOS DE DESTINO ---
    def _seleccionar_destino(self) -> None:
        inicio = str(self.carpeta_destino) if self.carpeta_destino else str(Path.home())
        carpeta = filedialog.askdirectory(title="Elige la carpeta donde se guardarán los archivos", initialdir=inicio, parent=self)
        
        if carpeta:
            self.carpeta_destino = Path(carpeta)
            self.lbl_destino.config(text=str(self.carpeta_destino), fg="blue")

    # --- MÉTODOS DE ORIGEN ---
    def _soltar_carpetas(self, event) -> None:
        rutas_arrastradas = self.tk.splitlist(event.data)
        nuevas = False
        
        for ruta_str in rutas_arrastradas:
            ruta = Path(ruta_str)
            if ruta not in self.carpetas_origen:
                self.carpetas_origen.append(ruta)
                nuevas = True
                
        if nuevas:
            self._refrescar_lista()

    def _refrescar_lista(self) -> None:
        self.lista.delete(0, tk.END)
        for carpeta in self.carpetas_origen:
            self.lista.insert(tk.END, str(carpeta))

    def _anadir_carpetas(self) -> None:
        inicio = f"{UNIDAD_WEBDAV}\\"
        while True:
            carpeta = filedialog.askdirectory(title="Añadir origen (Cancela para terminar)", initialdir=inicio, parent=self)
            if not carpeta:
                break
            
            ruta = Path(carpeta)
            if ruta not in self.carpetas_origen:
                self.carpetas_origen.append(ruta)
                self._refrescar_lista()
            inicio = str(ruta.parent)

    def _quitar_carpeta(self) -> None:
        seleccion = self.lista.curselection()
        if seleccion:
            del self.carpetas_origen[seleccion[0]]
            self._refrescar_lista()

    # --- GUARDADO ---
    def _guardar_y_cerrar(self) -> None:
        if not self.carpeta_destino:
            messagebox.showwarning("Falta destino", "Debes seleccionar una carpeta de destino para el PC.", parent=self)
            return

        if not self.carpetas_origen:
            if not messagebox.askyesno("Sin orígenes", "No has seleccionado carpetas a escanear.\n¿Guardar igualmente?", parent=self):
                return

        guardar_carpetas(self.carpetas_origen)
        guardar_destino(str(self.carpeta_destino))
        
        messagebox.showinfo("Guardado", "Configuración de origen y destino guardada correctamente.", parent=self)
        self.destroy()


def main() -> None:
    app = SelectorCarpetas()
    app.mainloop()


if __name__ == "__main__":
    main()