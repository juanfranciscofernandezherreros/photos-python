# HTTPS con Caddy

La aplicación debe permanecer detrás de un proxy HTTPS cuando se accede desde
fuera de la red local. La configuración incluida usa Caddy porque gestiona la
emisión y renovación de certificados de forma automática.

## Requisitos

1. Un dominio o subdominio cuyo registro `A`/`AAAA` apunte a la IP pública del
   servidor, por ejemplo `photos.example.com`.
2. Los puertos TCP 80 y TCP/UDP 443 dirigidos al servidor. No abras 8765,
   PostgreSQL, Grafana, Prometheus ni pgAdmin en el router.
3. Docker Compose y los secretos de la instalación normal ya configurados.

Si el proveedor usa CG-NAT o no puedes abrir esos puertos, usa una VPN privada
como WireGuard/Tailscale en lugar de publicar la aplicación sin TLS.

## Puesta en marcha

Define el dominio real en `.env`:

```dotenv
PHOTOS_DOMAIN=photos.example.com
```

Arranca el stack con el archivo adicional:

```bash
docker compose \
  -f docker-compose.yml \
  -f deploy/caddy/docker-compose.https.yml \
  up -d --build
```

Comprueba el estado y la obtención del certificado:

```bash
docker compose \
  -f docker-compose.yml \
  -f deploy/caddy/docker-compose.https.yml \
  ps
docker compose \
  -f docker-compose.yml \
  -f deploy/caddy/docker-compose.https.yml \
  logs --tail=100 caddy
curl --fail --show-error --head https://photos.example.com/health
```

El overlay establece `COOKIE_SECURE=true`, por lo que las cookies de sesión
solo viajan por HTTPS. Caddy reenvía `Host`, `X-Forwarded-For` y
`X-Forwarded-Proto` de forma predeterminada. Los certificados y claves se
guardan en el volumen `caddy_data`; inclúyelo en la estrategia de backup.

## Actualización y parada

Usa siempre ambos archivos para operar este despliegue:

```bash
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml pull
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml up -d --build
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml down
```

No uses `down -v`: eliminaría los volúmenes que conservan los certificados y
los datos de los servicios.
