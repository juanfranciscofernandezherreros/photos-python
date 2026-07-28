"""
Cuarto paso del pipeline: lee metadatos_screenshots.json, agrupa las fotos
por día (año/mes/día de captura) y genera un JSON nuevo (resumen_por_dia.json)
con el resumen de cada día, ordenado de más a menos fotos.
"""
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import METADATA_JSON, DAILY_SUMMARY_JSON
from .json_io import read_json, write_json

MetadatosCaptura = dict[str, Any]
ResumenDia = dict[str, Any]


def load_captures() -> list[MetadatosCaptura]:
    datos = read_json(METADATA_JSON, default=[])
    return datos if isinstance(datos, list) else []


def group_by_day(capturas: list[MetadatosCaptura]) -> list[ResumenDia]:
    grupos: dict[str, list[MetadatosCaptura]] = defaultdict(list)

    for captura in capturas:
        fecha_str = captura.get("fecha_captura")
        if not fecha_str:
            continue
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        grupos[fecha.strftime('%Y-%m-%d')].append(captura)

    resumenes: list[ResumenDia] = []

    for fecha_str, lista in grupos.items():
        ano, mes, dia = fecha_str.split('-')

        rutas_destino = {c["ruta_destino"] for c in lista if c.get("ruta_destino")}
        destino = str(Path(next(iter(rutas_destino))).parent) if rutas_destino else None

        rutas_zip = {c["ruta_zip"] for c in lista if c.get("ruta_zip")}
        ruta_zip = next(iter(rutas_zip)) if rutas_zip else None

        tamano_total_mb = round(sum(c.get("tamano_mb", 0) for c in lista), 2)

        resumenes.append({
            "fecha": fecha_str,
            "anio": ano,
            "mes": mes,
            "dia": dia,
            "cantidad_fotos": len(lista),
            "destino": destino,
            "ruta_zip": ruta_zip,
            "tamano_total_mb": tamano_total_mb,
            "ids": [c["id"] for c in lista if "id" in c],
            "archivos": [c["archivo"] for c in lista if c.get("archivo")],
        })

    resumenes.sort(key=lambda r: r["cantidad_fotos"], reverse=True)
    return resumenes


def generate_daily_summary() -> None:
    print(f"Reading '{METADATA_JSON}'...\n")

    capturas = load_captures()
    if not capturas:
        print(f"❌ No metadata found in '{METADATA_JSON}'. Run the previous steps first.")
        return

    resumenes = group_by_day(capturas)

    write_json(DAILY_SUMMARY_JSON, resumenes)

    print("-" * 50)
    print("SUMMARY BY DAY (most -> least photos):")
    for resumen in resumenes:
        print(f"  📅 {resumen['fecha']}  ->  {resumen['cantidad_fotos']} photos "
              f"({resumen['tamano_total_mb']} MB)")

    total_fotos = sum(r["cantidad_fotos"] for r in resumenes)
    print("-" * 50)
    print(f"✅ '{DAILY_SUMMARY_JSON}' generated with {len(resumenes)} days "
          f"and {total_fotos} photos in total.")


if __name__ == "__main__":
    generate_daily_summary()
