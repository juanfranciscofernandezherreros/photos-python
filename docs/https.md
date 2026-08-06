# HTTPS with Caddy

Keep Photos Sync behind an HTTPS reverse proxy whenever it is reachable outside a trusted local network. The included Caddy overlay automatically obtains and renews certificates.

## Requirements

1. A domain whose `A` or `AAAA` record points to the server, such as `photos.example.com`.
2. TCP port 80 and TCP/UDP port 443 forwarded to the server. Do not expose Photos Sync, PostgreSQL, Grafana, Prometheus, or pgAdmin directly.
3. A working base Docker Compose deployment with generated secrets.

If inbound ports are unavailable because of CG-NAT, use a private VPN such as WireGuard or Tailscale instead of publishing the application without TLS.

## Start the HTTPS deployment

Set the real domain in `.env`:

```dotenv
PHOTOS_DOMAIN=photos.example.com
```

```bash
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml up -d --build
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml ps
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml logs --tail=100 caddy
curl --fail --show-error --head https://photos.example.com/health
```

The overlay sets `COOKIE_SECURE=true`. Caddy forwards the standard proxy headers, while certificates and private keys remain in `caddy_data`; include that volume in the backup strategy.

## Update or stop

Always include both Compose files:

```bash
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml pull
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml up -d --build
docker compose -f docker-compose.yml -f deploy/caddy/docker-compose.https.yml down
```

Do not add `-v` to `down`; that would delete service data and certificates.
