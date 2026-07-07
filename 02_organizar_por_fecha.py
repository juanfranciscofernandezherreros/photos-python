import json
import shutil
from datetime import datetime
from pathlib import Path

from config import ARCHIVO_METADATOS_JSON, CARPETA_SCREENSHOTS_AGRUPADOS


def organizar_capturas_por_fecha():
    """Copia las capturas listadas en el JSON directamente desde Z: a
    CARPETA_SCREENSHOTS_AGRUPADOS/AAAA/MM/DD, en un único paso.

    Antes esto se hacía en dos copias (Z: -> screenshots -> screenshots
    _agrupados). Al fusionar los dos pasos, cada foto se copia una sola vez:
    la mitad de escrituras a disco y sin carpeta intermedia que mantener.
    """
    destino_base = CARPETA_SCREENSHOTS_AGRUPADOS

    if not Path(ARCHIVO_METADATOS_JSON).exists():
        print(f"❌ Error: No se encontró el archivo '{ARCHIVO_METADATOS_JSON}' en esta carpeta.")
        return

    print(f"Leyendo '{ARCHIVO_METADATOS_JSON}'...\n")
    print(f"Organizando capturas en: {destino_base.resolve()}")
    print("-" * 50)

    archivos_copiados = 0
    archivos_omitidos = 0
    errores = 0

    try:
        with open(ARCHIVO_METADATOS_JSON, 'r', encoding='utf-8') as f:
            lista_capturas = json.load(f)

        for captura in lista_capturas:
            ruta_origen = Path(captura["ruta_original"])

            # 1. Comprobamos que la imagen siga existiendo en Z:
            if not ruta_origen.exists():
                print(f"⚠️ No encontrado en Z: (¿Se borró?): {ruta_origen}")
                errores += 1
                continue

            try:
                # Usamos la fecha ya calculada en el paso 1 (fecha_captura),
                # así no hace falta volver a leer el archivo por su fecha.
                fecha = datetime.strptime(captura["fecha_captura"], '%Y-%m-%d %H:%M:%S')
                ano, mes, dia = fecha.strftime('%Y'), fecha.strftime('%m'), fecha.strftime('%d')

                carpeta_destino = destino_base / ano / mes / dia
                carpeta_destino.mkdir(parents=True, exist_ok=True)
                ruta_destino = carpeta_destino / captura["archivo"]

                # 2. Comprobamos si ya la habíamos copiado antes para no duplicar trabajo
                if ruta_destino.exists():
                    print(f"⏭️ Omitido (ya organizada): {captura['archivo']}")
                    archivos_omitidos += 1
                    continue

                # shutil.copy2 copia el archivo y mantiene la fecha de creación intacta
                shutil.copy2(ruta_origen, ruta_destino)
                print(f"📂 {captura['archivo']}  ->  {ano}/{mes}/{dia}/")
                archivos_copiados += 1

            except Exception as e:
                print(f"❌ Error al copiar '{captura['archivo']}': {e}")
                errores += 1

        print("-" * 50)
        print("RESUMEN DE LA ORGANIZACIÓN:")
        print(f"  - Archivos copiados y agrupados: {archivos_copiados}")
        print(f"  - Archivos omitidos (ya existían): {archivos_omitidos}")
        print(f"  - Errores de lectura/escritura: {errores}")

        if archivos_copiados > 0:
            print("\n✅ ¡Tus capturas se han copiado y ordenado correctamente!")

    except json.JSONDecodeError:
        print(f"❌ Error: El archivo '{ARCHIVO_METADATOS_JSON}' está corrupto o no tiene un formato JSON válido.")
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")


if __name__ == "__main__":
    organizar_capturas_por_fecha()
