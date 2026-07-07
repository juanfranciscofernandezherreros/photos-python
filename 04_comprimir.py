import shutil
from pathlib import Path

def comprimir_carpetas_por_dia():
    # ==========================================
    # CONFIGURACIÓN
    # ==========================================
    carpeta_base = Path(r"C:\Develop\screenshots")
    carpeta_zips = carpeta_base / "Comprimidos"
    # ==========================================
    
    if not carpeta_base.exists():
        print(f"❌ Error: La carpeta '{carpeta_base}' no existe.")
        return

    # Creamos la carpeta donde se guardarán los ZIP finales
    carpeta_zips.mkdir(parents=True, exist_ok=True)
    
    print(f"Buscando carpetas de días en: {carpeta_base.resolve()}...\n")
    print("-" * 50)
    
    zips_creados = 0
    errores = 0
    
    # Recorremos la estructura Año -> Mes -> Día
    for carpeta_ano in carpeta_base.iterdir():
        # Ignoramos archivos sueltos y la propia carpeta de Comprimidos
        if not carpeta_ano.is_dir() or carpeta_ano.name == "Comprimidos":
            continue
            
        for carpeta_mes in carpeta_ano.iterdir():
            if not carpeta_mes.is_dir():
                continue
                
            for carpeta_dia in carpeta_mes.iterdir():
                if not carpeta_dia.is_dir():
                    continue
                    
                # Extraemos los nombres de las carpetas para formar el nombre del ZIP
                ano = carpeta_ano.name
                mes = carpeta_mes.name
                dia = carpeta_dia.name
                
                nombre_archivo = f"Capturas_{ano}-{mes}-{dia}"
                ruta_base_zip = carpeta_zips / nombre_archivo
                
                # Comprobamos si el ZIP de ese día ya existe para no repetir trabajo
                if Path(f"{ruta_base_zip}.zip").exists():
                    print(f"⏭️ Omitido: '{nombre_archivo}.zip' ya existe.")
                    continue
                    
                try:
                    # shutil.make_archive crea el ZIP automáticamente
                    # Parámetros: ruta destino sin extensión, formato, ruta de la carpeta a comprimir
                    shutil.make_archive(
                        base_name=str(ruta_base_zip), 
                        format='zip', 
                        root_dir=str(carpeta_dia)
                    )
                    
                    print(f"📦 Comprimido: {ano}\\{mes}\\{dia} -> {nombre_archivo}.zip")
                    zips_creados += 1
                    
                except Exception as e:
                    print(f"❌ Error al comprimir el día {ano}-{mes}-{dia}: {e}")
                    errores += 1

    print("-" * 50)
    print("RESUMEN DE COMPRESIÓN:")
    print(f"  - Nuevos archivos ZIP creados: {zips_creados}")
    if errores > 0:
        print(f"  - Errores encontrados: {errores}")
        
    print(f"\n📁 Tus archivos comprimidos están listos en: {carpeta_zips.resolve()}")

if __name__ == "__main__":
    comprimir_carpetas_por_dia()