import subprocess
import sys
from pathlib import Path

# Carpeta donde vive este propio script. Todas las rutas se anclan aquí,
# así el orquestador funciona sin importar desde qué carpeta se ejecute.
CARPETA_SCRIPTS = Path(__file__).resolve().parent

def ejecutar_script(ruta_script):
    """Ejecuta un script de Python y comprueba si hay errores."""
    print(f"\n⏳ ['INICIANDO'] -> {ruta_script.name}")
    
    # Ejecutamos el script (cwd fijado a la carpeta de scripts por si alguno
    # usa rutas relativas, como el JSON de metadatos)
    resultado = subprocess.run([sys.executable, str(ruta_script)], cwd=CARPETA_SCRIPTS)
    
    if resultado.returncode != 0:
        print(f"\n❌ ['ERROR'] -> Fallo al ejecutar {ruta_script.name}.")
        return False
        
    print(f"✅ ['COMPLETADO'] -> {ruta_script.name}")
    return True

def orquestador_principal():
    # Lista de scripts disponibles, como rutas absolutas ancladas a esta carpeta
    pasos = [
        CARPETA_SCRIPTS / "01_descargar_archivos.py",
        CARPETA_SCRIPTS / "02_organizar_fotos.py",
        CARPETA_SCRIPTS / "03_agrupar.py",
        CARPETA_SCRIPTS / "04_comprimir.py",
    ]
    
    while True:
        print("\n" + "=" * 55)
        print("🚀 ORQUESTADOR DE PROCESOS - MENÚ PRINCIPAL")
        print("=" * 55)
        
        # Mostramos las opciones numeradas automáticamente
        for i, paso in enumerate(pasos, 1):
            print(f"  [{i}] - {paso.name}")
            
        print("-" * 55)
        print("  [T] - Ejecutar TODO en orden")
        print("  [S] - Salir del orquestador")
        print("=" * 55)
        
        opcion = input("\nElige una opción (ej: 1, 1,3, T o S): ").strip().upper()

        # Opción: Salir
        if opcion == 'S':
            print("\n👋 Saliendo del orquestador...")
            break
            
        rutas_a_ejecutar = []
        
        # Opción: Ejecutar todo
        if opcion == 'T':
            rutas_a_ejecutar = pasos
        # Opción: Ejecutar selecciones específicas
        else:
            try:
                # Convertimos la entrada en una lista de números (soporta comas o espacios)
                entradas = opcion.replace(' ', ',').split(',')
                indices = [int(x.strip()) for x in entradas if x.strip()]
                
                for indice in indices:
                    if 1 <= indice <= len(pasos):
                        rutas_a_ejecutar.append(pasos[indice - 1])
                    else:
                        print(f"\n⚠️ Ignorando opción '{indice}': Fuera de rango.")
            except ValueError:
                print("\n❌ Entrada no válida. Por favor, usa números, 'T' para todo o 'S' para salir.")
                continue

        # Si no hay nada que ejecutar, volvemos a mostrar el menú
        if not rutas_a_ejecutar:
            continue

        print("\n" + "=" * 55)
        print("⚙️ INICIANDO EJECUCIÓN")
        print("=" * 55)

        # 1. Comprobación de seguridad: Verificar que los archivos existen antes de empezar
        archivos_faltantes = False
        for paso in rutas_a_ejecutar:
            if not paso.exists():
                print(f"⚠️ ['ADVERTENCIA'] -> No se encuentra el archivo: {paso}")
                archivos_faltantes = True
        
        if archivos_faltantes:
            print("\n❌ Faltan scripts. Corrige las rutas o nombres antes de continuar.")
            continue # Volvemos al menú sin ejecutar nada

        # 2. Ejecución en cadena
        todos_exitosos = True
        for paso in rutas_a_ejecutar:
            exito = ejecutar_script(paso)
            
            # Si un script falla, detenemos la cadena para evitar que el siguiente cause un desastre
            if not exito:
                todos_exitosos = False
                print("\n🛑 Se detuvo la orquestación en cadena debido a un error previo.")
                break 

        if todos_exitosos:
            print("\n" + "=" * 55)
            print("🎉 TODOS LOS PASOS SELECCIONADOS SE HAN EJECUTADO CORRECTAMENTE")
            print("=" * 55)

if __name__ == "__main__":
    orquestador_principal()