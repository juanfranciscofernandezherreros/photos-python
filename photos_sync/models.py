"""
models.py — Typed data models for the Photos Sync pipeline.

Replaces the untyped dict[str, Any] aliases (MetadatosCaptura, ResumenDia)
that were scattered across download.py, organize.py, compress.py, and
summary.py with proper dataclasses.

Benefits:
- Typo-proof: captura.capture_date instead of captura["fecha_captura"]
- IDE autocomplete and mypy checking on all field access
- Single definition: change a field name here and every module updates
- to_dict() / from_dict() keep JSON serialization in one place
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Capture:
    """One screenshot / photo discovered during the scan step (download.py).

    Fields set at scan time (step 1):
      id              — stable UUID, persisted across runs
      filename        — bare filename, e.g. 'Screenshot_20231024_153020.png'
      extension       — lowercase without dot, e.g. 'png'
      size_mb         — file size in MB (2 decimal places)
      mtime           — filesystem modification timestamp (float, Unix epoch)
      capture_date    — best-effort capture datetime: 'YYYY-MM-DD HH:MM:SS'
      source_path     — absolute local path, or 'ssh://alias/remote/path'
      ssh_alias       — set only when source is an SSH server
      ssh_remote_path — set only when source is an SSH server

    Fields added at organize time (step 2):
      dest_path       — absolute local path after copying to YYYY/MM/DD/

    Fields added at compress time (step 3):
      zip_path        — absolute path to the .zip containing this file
    """
    id: str
    filename: str
    extension: str
    size_mb: float
    mtime: float
    capture_date: str
    source_path: str
    ssh_alias: Optional[str] = None
    ssh_remote_path: Optional[str] = None
    dest_path: Optional[str] = None
    zip_path: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    # ── serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to the JSON-compatible dict stored in METADATA_JSON.
        Keys match the original Spanish names for backwards compatibility
        with any existing metadata files."""
        d: dict = {
            "id":              self.id,
            "archivo":         self.filename,
            "formato":         self.extension,
            "tamano_mb":       self.size_mb,
            "mtime":           self.mtime,
            "fecha_captura":   self.capture_date,
            "ruta_original":   self.source_path,
        }
        if self.ssh_alias is not None:
            d["ssh_alias"] = self.ssh_alias
        if self.ssh_remote_path is not None:
            d["ssh_ruta_remota"] = self.ssh_remote_path
        if self.dest_path is not None:
            d["ruta_destino"] = self.dest_path
        if self.zip_path is not None:
            d["ruta_zip"] = self.zip_path
        if self.tags:
            d["tags"] = self.tags
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Capture":
        """Deserialize from the JSON dict stored in METADATA_JSON."""
        return cls(
            id=d.get("id", ""),
            filename=d.get("archivo", ""),
            extension=d.get("formato", ""),
            size_mb=d.get("tamano_mb", 0.0),
            mtime=d.get("mtime", 0.0),
            capture_date=d.get("fecha_captura", ""),
            source_path=d.get("ruta_original", ""),
            ssh_alias=d.get("ssh_alias"),
            ssh_remote_path=d.get("ssh_ruta_remota"),
            dest_path=d.get("ruta_destino"),
            zip_path=d.get("ruta_zip"),
            tags=d.get("tags", []),
        )


@dataclass
class DaySummary:
    """Aggregated summary for one calendar day (summary.py, step 4).

    Built by grouping Capture objects by their capture_date date part.
    """
    date: str          # 'YYYY-MM-DD'
    year: str
    month: str
    day: str
    photo_count: int
    total_mb: float
    dest_folder: Optional[str] = None   # local folder for that day
    zip_path: Optional[str] = None      # path to the day's .zip
    capture_ids: list[str] = field(default_factory=list)
    filenames: list[str] = field(default_factory=list)

    # ── serialization ─────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to the JSON-compatible dict stored in DAILY_SUMMARY_JSON.
        Keys match the original Spanish names for backwards compatibility."""
        return {
            "fecha":            self.date,
            "anio":             self.year,
            "mes":              self.month,
            "dia":              self.day,
            "cantidad_fotos":   self.photo_count,
            "tamano_total_mb":  self.total_mb,
            "destino":          self.dest_folder,
            "ruta_zip":         self.zip_path,
            "ids":              self.capture_ids,
            "archivos":         self.filenames,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DaySummary":
        """Deserialize from the JSON dict stored in DAILY_SUMMARY_JSON."""
        return cls(
            date=d.get("fecha", ""),
            year=d.get("anio", ""),
            month=d.get("mes", ""),
            day=d.get("dia", ""),
            photo_count=d.get("cantidad_fotos", 0),
            total_mb=d.get("tamano_total_mb", 0.0),
            dest_folder=d.get("destino"),
            zip_path=d.get("ruta_zip"),
            capture_ids=d.get("ids", []),
            filenames=d.get("archivos", []),
        )
