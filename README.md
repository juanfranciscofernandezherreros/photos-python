# Photos Sync

Sincroniza fotos desde el móvil (WebDAV / SSH), las organiza por fecha, clasifica por etiquetas y las almacena local o en servidor remoto.

## Inicio rápido con Docker

```bash
cp .env.example .env
python scripts/generate_secrets.py
docker compose up -d
```

Abre **http://localhost:8765**

## Actualizar a la última versión

**IMPORTANTE:** si ya tenías la app corriendo, Docker no reconstruye la
imagen por sí solo cuando cambia el código Python. Después de descomprimir
una versión nueva del proyecto, ejecuta:

```bash
docker compose down
docker compose build --no-cache app
docker compose up -d
```

O más rápido y equivalente:

```bash
docker compose up -d --build --force-recreate
```

Si sospechas que la BD ha quedado en mal estado (fotos que no aparecen,
usuarios raros, etc.), puedes empezar de cero conservando las fotos:

```bash
docker compose down -v      # -v borra el volumen postgres_data
docker compose up -d --build
```

Con `-v` se borra la base de datos entera; la primera vez que abras la app
te pedirá crear el administrador otra vez. Las **fotos en tu `PHOTOS_DIR` NO
se tocan**, solo la BD. Después de esto puedes reingestar via WebDAV o
ejecutar el Pipeline sobre tus carpetas existentes.

### Verificar que la BD tiene datos

Con el admin logueado, visita **http://localhost:8765/api/diag** — muestra
el número de filas en cada tabla:

```json
{
  "db_dialect": "postgresql",
  "counts": {
    "captures": 42,
    "day_summaries": 5,
    "source_folders": 1,
    "users": 1,
    ...
  }
}
```

Si `captures` es 0 después de descargar fotos, algo va mal — comparte esa
salida.

## Variables de entorno (`.env`)

| Variable | Por defecto | Descripción |
|---|---|---|
| `PHOTOS_DIR` | `./photos` | Carpeta del host con las fotos |
| `APP_PORT` | `8765` | Puerto del dashboard web |
| `APP_BIND_IP` | `127.0.0.1` | Interfaz donde escucha el dashboard |
| `DB_BIND_IP` | `127.0.0.1` | Interfaz donde se publica PostgreSQL |
| `SECRETS_DIR` | `./secrets` | Directorio local de Docker Secrets |

## Observabilidad: Grafana, Prometheus y Loki

Arranca la aplicación y el stack completo con:

```bash
docker compose --profile monitoring up -d --build
```

- Aplicación: <http://localhost:8765>
- Grafana: <http://localhost:3000>
- Prometheus: <http://localhost:9090>

Grafana se aprovisiona automáticamente con las fuentes **Prometheus** y
**Loki** y con dos dashboards dentro de la carpeta `Photos Sync`:

- `API REST · Observabilidad`: dashboard de API con KPIs, tráfico, análisis por
  endpoint/método/código HTTP, logs y trazabilidad por `correlation_id`.
- `Hardware e Infraestructura`: dashboard independiente con salud de servicios,
  CPU, RAM, red, disco, uptime de contenedores y estado de PostgreSQL.

El panel **Logs de cada petición** muestra timestamp, método, endpoint, código
HTTP, duración y `correlation_id` para cada petición.

La primera instalación usa `GRAFANA_ADMIN_USER` y
`secrets/grafana_admin_password.txt`. Cambiar ese archivo no modifica una
contraseña que ya esté guardada en el volumen. Para restablecerla:

```bash
docker exec photos_grafana grafana cli admin reset-admin-password NuevaClaveSegura
```

Consultas útiles en **Explore → Loki**:

```logql
# Todas las peticiones completadas
{service="mi-api"} | json | message="HTTP request completed"

# Solo errores HTTP
{service="mi-api"} | json | message="HTTP request completed" | status_code >= 400

# Trazar una petición concreta
{service="mi-api"} | json | correlation_id="req_..."
```

Para contar las peticiones del intervalo seleccionado en Grafana, usa
Prometheus:

```promql
sum(increase(http_requests_total{service="mi-api"}[$__range]))
```

Las métricas usan la plantilla de la ruta (`/api/days/{date}/photos`) para
evitar una serie distinta por fecha. Los logs de acceso no registran cuerpos,
cookies, cabeceras de autenticación ni parámetros de consulta. Loki conserva
14 días de logs y Prometheus 15 días de métricas por defecto; ambas retenciones
se pueden ajustar desde `.env`/los archivos de `monitoring/`.

Comprobar el estado o detener el stack:

```bash
docker compose --profile monitoring ps
docker compose --profile monitoring down
```

## pgAdmin (opcional)

```bash
docker compose --profile admin up -d
# http://localhost:5050  →  host: db, puerto: 5432
```

## Migrar datos JSON existentes

```bash
docker compose exec app python migrations/import_from_json.py
```

## Migraciones automáticas de PostgreSQL

Cada arranque del contenedor ejecuta Alembic antes de servir tráfico. Una base
nueva se crea desde cero y una instalación anterior sin `alembic_version` se
adopta automáticamente antes de aplicar únicamente las revisiones pendientes.
El historial actual incluye el esquema base, la normalización de fechas e
índices y la retirada de la columna antigua `city`.

Haz un backup antes de actualizar entre versiones. Si una migración falla, la
aplicación no continúa con un esquema incompleto. Los SQL de `migrations/` se
conservan como herramientas históricas y de recuperación; ya no forman parte
del procedimiento normal de despliegue.

## Desarrollo local

```bash
pip install -e ".[dev,ssh,images]"
export DATABASE_URL_FILE=/ruta/segura/database_url.txt
python -m photos_sync
```

## Tests

```bash
python -m pytest tests -q
```

La cobertura incluye ramas y tiene una barrera mínima del 80 %. El comando
genera un informe navegable en `reports/coverage/index.html` y otro en XML:

```bash
python -m pytest tests -q --cov=photos_sync --cov-branch \
  --cov-report=term-missing --cov-report=html --cov-report=xml \
  --cov-fail-under=80
```

La suite de contratos Cucumber ejecuta todos los endpoints HTTP y WebSocket
contra una API y una base SQLite temporales. Maven no necesita estar instalado:

```bash
cd serenity
./mvnw verify       # Linux/macOS
mvnw.cmd verify     # Windows
```

El reporte queda en `serenity/target/site/serenity/index.html`. Cada escenario
muestra la request y la response reales (URL, método, cuerpo, estado y tipo de
contenido); contraseñas y cookies se enmascaran. Una prueba de catálogo compara
el feature con los decoradores de FastAPI, por lo que CI falla si se añade una
ruta sin su escenario Serenity. Los dos reportes se publican también como
artefactos de GitHub Actions durante 14 días.

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

Los secretos de sesión, PostgreSQL, Grafana y pgAdmin se generan localmente:

```bash
python scripts/generate_secrets.py
```

El directorio `secrets/` está excluido de Git y del contexto de build. Si
cambia `app_secret_key.txt`, todas las sesiones de la aplicación se cierran.

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
