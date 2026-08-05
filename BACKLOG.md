# Photos Sync — Backlog

Estado actualizado tras incorporar CI, seguridad, rendimiento, observabilidad,
Alembic y pruebas de recuperación. Los tickets terminados se mantienen al final
para que el documento también sirva como historial técnico.

## Prioridad alta

### PS-15 · Probar flujos positivos de servicios externos

Los contratos Serenity alcanzan todos los endpoints, pero SSH y algunas rutas
WebDAV usan respuestas controladas o recursos inexistentes. Añadir servidores
fake reproducibles para probar conexión, escaneo, descarga, reintento y
reanudación de principio a fin.

### PS-16 · Configurar entrega de alertas

Prometheus ya evalúa reglas de disponibilidad, errores, latencia, jobs y
capacidad. Falta incorporar Alertmanager o un contact point equivalente y
documentar un destino de notificaciones opt-in para cada instalación.

### PS-17 · Probar actualización desde esquemas históricos

Alembic adopta bases existentes y CI prueba PostgreSQL 16 desde cero. Conservar
fixtures anonimizadas de cada esquema publicado para verificar todas las rutas
de actualización, no solo la revisión actual.

## Prioridad media

### PS-18 · Modularizar el frontend

`photos_sync/web/static/index.html` concentra HTML, CSS y JavaScript. Separar
los módulos por dominio y añadir lint/pruebas del navegador sin introducir una
cadena de build pesada para el despliegue self-hosted.

### PS-19 · Dividir el repositorio de datos

`photos_sync/repository.py` contiene consultas de galería, álbumes, usuarios,
papelera y configuración. Dividirlo por dominio manteniendo una API de acceso
estable y transacciones explícitas.

### PS-20 · Programación opcional del pipeline

Permitir una planificación sencilla para sincronizaciones nocturnas, con
historial de últimas ejecuciones y sin obligar a desplegar un scheduler externo.

## Completado

| Área | Resultado |
|---|---|
| CI | Ruff, mypy, Python 3.11/3.12, cobertura, Serenity, PostgreSQL y build con gate obligatorio |
| Pruebas | Más de 370 tests, cobertura mínima del 80 % y catálogo completo de endpoints |
| BDD | Reporte Serenity HTML con request/response saneadas para HTTP y WebSocket |
| Base de datos | PostgreSQL, operaciones bulk, `capture_day`, índices y Alembic automático |
| Recuperación | Backups diarios y prueba destructiva aislada de dump/restauración |
| Seguridad | Secretos montados, bcrypt, bloqueo, rate limiting y comandos sin shell injection |
| WebDAV | Descarga concurrente configurable, lotes de persistencia y progreso observable |
| SSH | Escaneo paralelo, reintentos y reconexión de transferencias |
| Observabilidad | Métricas, logs estructurados, Prometheus, Grafana, Loki y alertas reales |
| Frontend | HTML estático extraído del servidor Python, galería, álbumes, favoritos y papelera |
| Documentación | Docker, migraciones, pruebas, backups, restauración y operación documentados |
