# Photos Sync

Sincroniza fotos desde el móvil (WebDAV / SSH), las organiza por fecha, clasifica por etiquetas y ciudad (GPS EXIF), y las almacena local o en servidor remoto.

## Inicio rápido con Docker

```bash
cp .env.example .env
docker compose up -d
```

Abre **http://localhost:8765**

## Variables de entorno (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | `photos2024` | Contraseña PostgreSQL |
| `PHOTOS_DIR` | `./photos` | Carpeta del host con las fotos |
| `APP_PORT` | `8765` | Puerto del dashboard web |

## pgAdmin (opcional)

```bash
docker compose --profile admin up -d
# http://localhost:5050  →  host: db, puerto: 5432
```

## Migrar datos JSON existentes

```bash
docker compose exec app python migrations/import_from_json.py
```

## Desarrollo local

```bash
pip install -e ".[dev,ssh,images]"
export DATABASE_URL=postgresql://photos:photos2024@localhost/photos_sync
python -m photos_sync
```

## Tests

```bash
pytest tests/
# 223 passed
```

## Usuarios y login

Al abrir la app por primera vez, aparece una pantalla para **crear el
administrador**. Solo puede existir un administrador (garantizado por la
base de datos).

- El **administrador** puede: configurar carpetas/SSH/WebDAV, ejecutar el
  pipeline y registrar/borrar usuarios.
- Los **usuarios normales** solo pueden ver la galería, álbumes y ciudades
  (biblioteca compartida — todos ven las mismas fotos).

El admin registra nuevos usuarios desde la pestaña **Users**.

Cada usuario puede cambiar su propia contraseña desde el menú de su avatar
(arriba a la derecha) → Change password.

**Importante:** define `SECRET_KEY` en el `.env` con una cadena larga y
aleatoria. Si cambia, todas las sesiones se cierran. Generar una:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Backups automáticos

El servicio `backup` del compose ejecuta `pg_dump` cada 24 horas y guarda
los dumps comprimidos en `./backups/` (o en `BACKUP_DIR` si lo cambias en `.env`).
Se conservan los últimos `BACKUP_KEEP_DAYS` días (por defecto 7); los más
antiguos se borran automáticamente.

Ficheros generados: `photos_sync_YYYYMMDD_HHMMSS.sql.gz`

### Forzar un backup ahora

```bash
docker compose exec backup sh -c "
  pg_dump --no-password | gzip > /backups/manual_$(date +%Y%m%d_%H%M%S).sql.gz
"
```

### Restaurar un backup

```bash
# 1. Elige el fichero a restaurar
ls backups/

# 2. Restaura (para y borra los datos actuales)
docker compose stop app
docker compose exec -T db psql -U photos -c "DROP DATABASE photos_sync; CREATE DATABASE photos_sync;"
gunzip -c backups/photos_sync_20240101_030000.sql.gz | docker compose exec -T db psql -U photos photos_sync
docker compose start app
```

### Ver logs del backup

```bash
docker compose logs backup --tail=20
```

## Papelera (Trash)

Las fotos borradas no se eliminan de inmediato: se mueven a la papelera,
desde donde puedes **restaurarlas** a su ubicación original o **borrarlas
definitivamente**.

- Pestaña **Trash** en el menú lateral (con contador).
- Selecciona fotos → **Restore** (vuelven a su carpeta) o **Delete forever**.
- **Empty trash** vacía toda la papelera de golpe.
- Purga automática: el admin puede llamar a `POST /api/trash/purge-old?days=30`
  para borrar definitivamente lo que lleve más de 30 días en la papelera.
