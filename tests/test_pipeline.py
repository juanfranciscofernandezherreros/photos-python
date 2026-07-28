"""
Tests del pipeline: download, organizar, comprimir, resumen.
──────────────────────────────────────────────────────────────
No se testea la conexión real a móviles ni a servidores SSH (requeriría
hardware externo). Sí se testea toda la lógica que opera sobre archivos
locales: extracción de fecha del nombre, organización por AAAA/MM/DD,
compresión en ZIPs, y generación del resumen JSON.
"""
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

import pytest

from photos_sync.download import get_actual_date, load_existing_metadata
from photos_sync.summary import group_by_day, generate_daily_summary
from photos_sync.compress import zip_is_valid, compress_folders_by_day
from photos_sync.organize import organize_captures_by_date
from photos_sync.config import (
    METADATA_JSON, DAILY_SUMMARY_JSON,
    VALID_EXTENSIONS,
)


# ═══════════════════════════════ get_actual_date ══════════════════════════

class TestObtenerFechaReal:
    def test_nombre_con_fecha_y_hora_completa(self):
        f = get_actual_date("Screenshot_20231024_153020.png", 0)
        assert f == "2023-10-24 15:30:20"

    def test_nombre_con_guiones(self):
        f = get_actual_date("Screenshot_2023-10-24-15-30-20.png", 0)
        assert f == "2023-10-24 15:30:20"

    def test_nombre_solo_fecha(self):
        f = get_actual_date("foto_20231024.jpg", 0)
        assert f == "2023-10-24 12:00:00"

    def test_nombre_sin_fecha_usa_mtime(self):
        mtime = datetime(2022, 5, 15, 10, 0, 0).timestamp()
        f = get_actual_date("img_sin_fecha.png", mtime)
        assert f.startswith("2022-05-15")

    def test_mes_invalido_usa_mtime(self):
        mtime = datetime(2022, 1, 1).timestamp()
        f = get_actual_date("Screenshot_20231399_153020.png", mtime)
        assert f.startswith("2022-")

    def test_dia_invalido_usa_mtime(self):
        mtime = datetime(2022, 1, 1).timestamp()
        f = get_actual_date("Screenshot_20231200_153020.png", mtime)
        assert f.startswith("2022-")

    def test_formatos_de_extensiones_validas(self):
        for ext in VALID_EXTENSIONS:
            nombre = f"Screenshot_20230101_120000{ext}"
            f = get_actual_date(nombre, 0)
            assert f == "2023-01-01 12:00:00", f"failed with extension {ext}"


# ═══════════════════════════════ load_existing_metadata ═════════════════

class TestCargarMetadatosExistentes:
    def test_sin_archivo_devuelve_vacio(self):
        assert load_existing_metadata() == {}

    def test_carga_correctamente(self, tmp_path, metadatos_json):
        m = load_existing_metadata()
        assert len(m) == 2
        for clave, valor in m.items():
            assert "ruta_original" in valor
            assert valor["ruta_original"] == clave

    def test_archivo_corrupto_devuelve_vacio(self, tmp_path):
        (tmp_path / METADATA_JSON).write_text("no es json", encoding="utf-8")
        assert load_existing_metadata() == {}


# ═══════════════════════════════ organize_captures_by_date ════════════════

class TestOrganizarCapturas:
    def test_organiza_en_carpetas_por_fecha(self, tmp_path, metadatos_json):
        # Crear los archivos físicos de origen
        for nombre in ["Screenshot_20231024_153020.png", "Screenshot_20231025_090000.jpg"]:
            (tmp_path / nombre).write_bytes(b"fake")

        from photos_sync import folders as _carpetas
        _folders.save_destination(str(tmp_path / "organizado"))
        organize_captures_by_date()

        assert (tmp_path / "organizado" / "2023" / "10" / "24" / "Screenshot_20231024_153020.png").exists()
        assert (tmp_path / "organizado" / "2023" / "10" / "25" / "Screenshot_20231025_090000.jpg").exists()

    def test_no_duplica_si_ya_existe(self, tmp_path, metadatos_json):
        for nombre in ["Screenshot_20231024_153020.png", "Screenshot_20231025_090000.jpg"]:
            (tmp_path / nombre).write_bytes(b"fake")

        from photos_sync import folders as _carpetas
        _folders.save_destination(str(tmp_path / "organizado"))

        organize_captures_by_date()
        organize_captures_by_date()  # segunda vez no debe duplicar

        archivos = list((tmp_path / "organizado").rglob("*.png"))
        assert len(archivos) == 1

    def test_sin_metadatos_no_falla(self):
        organize_captures_by_date()  # solo imprime el aviso, no lanza

    def test_actualiza_ruta_destino_en_metadatos(self, tmp_path, metadatos_json):
        for nombre in ["Screenshot_20231024_153020.png", "Screenshot_20231025_090000.jpg"]:
            (tmp_path / nombre).write_bytes(b"fake")

        from photos_sync import folders as _carpetas
        _folders.save_destination(str(tmp_path / "organizado"))
        organize_captures_by_date()

        datos = json.loads(metadatos_json.read_text())
        assert all("ruta_destino" in c for c in datos)


# ═══════════════════════════════ compress_folders_by_day ══════════════════

class TestComprimir:
    def test_crea_zip_por_dia(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _carpetas
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()

        zips = list((carpeta_organizada / "Comprimidos").glob("*.zip"))
        assert len(zips) == 2  # un zip por cada día del fixture

    def test_zip_valido(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _carpetas
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()

        for z in (carpeta_organizada / "Comprimidos").glob("*.zip"):
            assert zip_is_valid(z), f"{z.name} no pasó la verificación de integridad"

    def test_no_duplica_zips_existentes(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _carpetas
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()
        compress_folders_by_day()  # segunda vez, no debe duplicar

        zips = list((carpeta_organizada / "Comprimidos").glob("*.zip"))
        assert len(zips) == 2

    def test_zip_is_valid_con_zip_real(self, tmp_path):
        z = tmp_path / "test.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.txt", "contenido")
        assert zip_is_valid(z)

    def test_zip_is_valid_con_archivo_corrupto(self, tmp_path):
        z = tmp_path / "malo.zip"
        z.write_bytes(b"esto no es un zip")
        assert not zip_is_valid(z)

    def test_sin_carpeta_base_no_falla(self):
        compress_folders_by_day()  # solo imprime el aviso


# ═══════════════════════════════ resumen ════════════════════════════════════

class TestResumen:
    def test_group_by_day_agrupa_correctamente(self):
        capturas = [
            {"id": "1", "archivo": "a.png", "fecha_captura": "2023-10-24 10:00:00", "tamano_mb": 1.0},
            {"id": "2", "archivo": "b.png", "fecha_captura": "2023-10-24 11:00:00", "tamano_mb": 2.0},
            {"id": "3", "archivo": "c.png", "fecha_captura": "2023-10-25 09:00:00", "tamano_mb": 0.5},
        ]
        resumenes = group_by_day(capturas)
        assert len(resumenes) == 2
        dia_24 = next(r for r in resumenes if r["fecha"] == "2023-10-24")
        assert dia_24["cantidad_fotos"] == 2
        assert dia_24["tamano_total_mb"] == pytest.approx(3.0)

    def test_agrupar_ordena_por_cantidad_desc(self):
        capturas = [
            {"id": "1", "archivo": "a.png", "fecha_captura": "2023-10-24 10:00:00", "tamano_mb": 1.0},
            {"id": "2", "archivo": "b.png", "fecha_captura": "2023-10-25 09:00:00", "tamano_mb": 0.5},
            {"id": "3", "archivo": "c.png", "fecha_captura": "2023-10-25 10:00:00", "tamano_mb": 0.5},
        ]
        resumenes = group_by_day(capturas)
        assert resumenes[0]["fecha"] == "2023-10-25"  # 2 fotos > 1 foto

    def test_agrupar_ignora_capturas_sin_fecha(self):
        capturas = [
            {"id": "1", "archivo": "a.png", "fecha_captura": None, "tamano_mb": 1.0},
            {"id": "2", "archivo": "b.png", "fecha_captura": "", "tamano_mb": 1.0},
        ]
        assert group_by_day(capturas) == []

    def test_agrupar_ignora_fecha_malformada(self):
        capturas = [{"id": "1", "archivo": "a.png", "fecha_captura": "no-es-fecha", "tamano_mb": 1.0}]
        assert group_by_day(capturas) == []

    def test_generar_resumen_crea_archivo(self, tmp_path, metadatos_json):
        generate_daily_summary()
        resumen_path = tmp_path / DAILY_SUMMARY_JSON
        assert resumen_path.exists()
        datos = json.loads(resumen_path.read_text())
        assert len(datos) == 2

    def test_generar_resumen_sin_metadatos_no_falla(self):
        generate_daily_summary()  # solo imprime aviso

    def test_resumen_incluye_ruta_zip(self, tmp_path, carpeta_organizada, metadatos_json):
        from photos_sync import folders as _carpetas
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()
        generate_daily_summary()

        resumen_path = tmp_path / DAILY_SUMMARY_JSON
        datos = json.loads(resumen_path.read_text())
        # Al menos un día debe tener ruta_zip rellenada
        assert any(r.get("ruta_zip") for r in datos)
