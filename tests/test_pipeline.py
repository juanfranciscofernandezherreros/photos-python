"""
Tests for the pipeline: download, organize, compress, summary.
──────────────────────────────────────────────────────────────
Does not test real connections to phones or SSH servers (would require
external hardware). Tests all logic that operates on local files: date
extraction from filename, organization by YYYY/MM/DD, ZIP compression,
and JSON summary generation.
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
    def test_no_file_returns_empty(self):
        assert load_existing_metadata() == {}

    def test_carga_correctamente(self, tmp_path, metadatos_json):
        m = load_existing_metadata()
        assert len(m) == 2
        for source_path, capture in m.items():
            assert capture.source_path == source_path
            assert capture.filename != ""

    def test_corrupt_file_returns_empty(self, tmp_path):
        from photos_sync.config import METADATA_JSON as MJ
        Path(MJ).write_text("no es json", encoding="utf-8")
        assert load_existing_metadata() == {}


# ═══════════════════════════════ organize_captures_by_date ════════════════

class TestOrganizarCapturas:
    def test_organiza_en_carpetas_por_fecha(self, tmp_path, metadatos_json):
        # Crear los archivos físicos de origen
        for nombre in ["Screenshot_20231024_153020.png", "Screenshot_20231025_090000.jpg"]:
            (tmp_path / nombre).write_bytes(b"fake")

        from photos_sync import folders as _folders
        _folders.save_destination(str(tmp_path / "organizado"))
        organize_captures_by_date()

        assert (tmp_path / "organizado" / "2023" / "10" / "24" / "Screenshot_20231024_153020.png").exists()
        assert (tmp_path / "organizado" / "2023" / "10" / "25" / "Screenshot_20231025_090000.jpg").exists()

    def test_no_duplica_si_ya_existe(self, tmp_path, metadatos_json):
        for nombre in ["Screenshot_20231024_153020.png", "Screenshot_20231025_090000.jpg"]:
            (tmp_path / nombre).write_bytes(b"fake")

        from photos_sync import folders as _folders
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

        from photos_sync import folders as _folders
        _folders.save_destination(str(tmp_path / "organizado"))
        organize_captures_by_date()

        datos = json.loads(metadatos_json.read_text())
        assert all("ruta_destino" in c for c in datos)


# ═══════════════════════════════ compress_folders_by_day ══════════════════

class TestComprimir:
    def test_crea_zip_por_dia(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _folders
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()

        zips = list((carpeta_organizada / "Comprimidos").glob("*.zip"))
        assert len(zips) == 2  # un zip por cada día del fixture

    def test_zip_valido(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _folders
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()

        for z in (carpeta_organizada / "Comprimidos").glob("*.zip"):
            assert zip_is_valid(z), f"{z.name} no pasó la verificación de integridad"

    def test_no_duplica_zips_existentes(self, tmp_path, carpeta_organizada):
        from photos_sync import folders as _folders
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

    def test_zip_is_valid_with_corrupt_file(self, tmp_path):
        z = tmp_path / "malo.zip"
        z.write_bytes(b"esto no es un zip")
        assert not zip_is_valid(z)

    def test_sin_carpeta_base_no_falla(self):
        compress_folders_by_day()  # solo imprime el aviso


# ═══════════════════════════════ resumen ════════════════════════════════════

class TestResumen:
    def _make_capture(self, id, filename, date, size_mb):
        from photos_sync.models import Capture
        return Capture(id=id, filename=filename, extension="png", size_mb=size_mb,
                       mtime=0.0, capture_date=date, source_path=f"/{filename}")

    def test_group_by_day_groups_correctly(self):
        captures = [
            self._make_capture("1", "a.png", "2023-10-24 10:00:00", 1.0),
            self._make_capture("2", "b.png", "2023-10-24 11:00:00", 2.0),
            self._make_capture("3", "c.png", "2023-10-25 09:00:00", 0.5),
        ]
        summaries = group_by_day(captures)
        assert len(summaries) == 2
        day_24 = next(s for s in summaries if s.date == "2023-10-24")
        assert day_24.photo_count == 2
        assert day_24.total_mb == pytest.approx(3.0)

    def test_group_by_day_sorts_by_count_desc(self):
        captures = [
            self._make_capture("1", "a.png", "2023-10-24 10:00:00", 1.0),
            self._make_capture("2", "b.png", "2023-10-25 09:00:00", 0.5),
            self._make_capture("3", "c.png", "2023-10-25 10:00:00", 0.5),
        ]
        summaries = group_by_day(captures)
        assert summaries[0].date == "2023-10-25"  # 2 photos > 1 photo

    def test_group_by_day_ignores_captures_without_date(self):
        captures = [
            self._make_capture("1", "a.png", "", 1.0),
            self._make_capture("2", "b.png", "", 1.0),
        ]
        assert group_by_day(captures) == []

    def test_group_by_day_ignores_malformed_date(self):
        captures = [self._make_capture("1", "a.png", "not-a-date", 1.0)]
        assert group_by_day(captures) == []

    def test_generate_summary_creates_file(self, tmp_path, metadatos_json):
        generate_daily_summary()
        from photos_sync.config import DAILY_SUMMARY_JSON as DSJ
        resumen_path = Path(DSJ)
        assert resumen_path.exists()
        datos = json.loads(resumen_path.read_text())
        assert len(datos) == 2

    def test_generate_summary_without_metadata_does_not_fail(self):
        generate_daily_summary()  # solo imprime aviso

    def test_summary_includes_zip_path(self, tmp_path, carpeta_organizada, metadatos_json):
        from photos_sync import folders as _folders
        _folders.save_destination(str(carpeta_organizada))
        compress_folders_by_day()
        generate_daily_summary()

        from photos_sync.config import DAILY_SUMMARY_JSON as DSJ
        resumen_path = Path(DSJ)
        datos = json.loads(resumen_path.read_text())
        # At least one day must have ruta_zip filled in
        assert any(r.get("ruta_zip") for r in datos)
