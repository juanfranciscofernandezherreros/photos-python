"""Punto de entrada de la aplicación gráfica.

Antes: abría el selector de carpetas y, al cerrarlo, seguía todo el
pipeline por consola con print(). Ahora: abre una única ventana con
botones para cada paso y un panel de log integrado — nada se ejecuta
en la terminal.

Uso:
    python app.py
"""
from photos_sync.main_window import main

if __name__ == "__main__":
    main()
