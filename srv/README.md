# Homelab Infrastructure & Docker Services Guide

This guide documents the Docker services architecture, domain routing via Traefik reverse proxy, and step-by-step procedures for deploying, maintaining, and decommissioning services on this server.

---

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Current Services & Port Registry](#2-current-services--port-registry)
3. [How Traefik Domain Routing Works](#3-how-traefik-domain-routing-works)
4. [Step-by-Step: Adding a New Service](#4-step-by-step-adding-a-new-service)
5. [Step-by-Step: Removing an Existing Service](#5-step-by-step-removing-an-existing-service)
6. [Alternative Routing Method: Docker Labels](#6-alternative-routing-method-docker-labels)
7. [Maintenance & Troubleshooting Playbook](#7-maintenance--troubleshooting-playbook)

---

## 1. Architecture Overview

### Topology Diagram

```mermaid
flowchart TD
    Client["Client Devices (Browser / Apps)"]
    DNS["Technitium DNS Server\n(Port 53 / dns.nominomi.lan)\nResolves *.nominomi.lan -> 192.168.1.12"]
    
    subgraph HostServer["Host Server (192.168.1.12)"]
        subgraph TraefikContainer["Traefik v3.1 Reverse Proxy"]
            EP_HTTP["Entrypoint: web (Port 80)"]
            EP_HTTPS["Entrypoint: websecure (Port 443)\nTLS: nominomi.lan cert"]
            EP_DASH["Entrypoint: traefik (Port 8080)\nTraefik Dashboard"]
            RoutesWatcher["File Provider\nWatches /srv/docker/traefik/routes.yml"]
        end

        subgraph DockerServices["Docker Services (/srv/docker/*)"]
            CasaOS["CasaOS (:1268)"]
            Sonarr["Sonarr (:8989)"]
            Radarr["Radarr (:7878)"]
            Prowlarr["Prowlarr (:9696)"]
            Qbit["qBittorrent (:8181)"]
            Jellyfin["Jellyfin (:8097)"]
            Jellyseerr["Jellyseerr (:5055)"]
            HomeAssistant["Home Assistant (:8123)"]
            Portainer["Portainer (:9443 HTTPS)"]
            Glance["Glance (:8082)"]
            Sparky["Sparkyfitness (:3004)"]
            Bazarr["Bazarr (:6767)"]
            MeTube["MeTube (:8081)"]
            Rustdesk["Rustdesk Server (Host net)"]
        end
    end

    Client -->|1. Query DNS| DNS
    DNS -->|Returns 192.168.1.12| Client
    Client -->|2. HTTP Request (Host: <app>.nominomi.lan)| EP_HTTP
    Client -->|2. HTTPS Request (Host: <app>.nominomi.lan)| EP_HTTPS
    Client -->|Dashboard Access| EP_DASH

    RoutesWatcher -.->|Loads Routing Rules| TraefikContainer
    EP_HTTP -->|Reverse Proxy HTTP| DockerServices
    EP_HTTPS -->|Reverse Proxy HTTPS / TLS pass| DockerServices
```

### Core Components

| Component | Path / Location | Purpose |
| :--- | :--- | :--- |
| **Host IP** | `192.168.1.12` | Static LAN IP for the home server. |
| **Local Domain** | `*.nominomi.lan` | Base wildcard domain used across all internal applications. |
| **DNS Server** | `dns.nominomi.lan` (Port 53) | Technitium DNS running locally on host network. Resolves `*.nominomi.lan` to `192.168.1.12`. |
| **Reverse Proxy** | `/srv/docker/traefik/compose.yml` | Traefik v3.1 handling HTTP (80), HTTPS (443), and Dashboard (8080). |
| **Dynamic Routes** | `/srv/docker/traefik/routes.yml` | Dynamic YAML routing table watched by Traefik. Changes reload automatically without restarting Traefik. |
| **TLS Certificates** | `/srv/docker/traefik/certs/` | Contains `nominomi.lan.crt` and `nominomi.lan.key` used as default wildcard certificate. |
| **Docker Base Dir** | `/srv/docker/` | Contains individual subdirectories for each deployed application. |

---

## 2. Current Services & Port Registry

Before adding a new container, refer to this table to avoid port collisions:

| Subdomain | Internal URL | Container Name | Compose Directory | Protocol / Notes |
| :--- | :--- | :--- | :--- | :--- |
| `dns.nominomi.lan` | `http://192.168.1.12:5380` | `technitium` | `/srv/docker/technitium` | HTTP (DNS UI, Host Network) |
| `assistant.nominomi.lan`| `http://192.168.1.12:8123` | `home-assistant` | `/srv/docker/big-bear-home-assistant` | HTTP (Host Network) |
| `portainer.nominomi.lan`| `https://portainer:9443` | `portainer` | `/srv/docker/portainer` | HTTPS (`websecure`, `traefik_proxy`) |
| `glance.nominomi.lan` | `http://glance:8080` | `glance` | `/srv/docker/glance` | HTTP (`traefik_proxy`) |
| `jellyfin.nominomi.lan` | `http://jellyfin:8096` | `jellyfin` | `/srv/docker/jellyfin-nvidia` | HTTP (GPU pass, `traefik_proxy`) |
| `jellyseerr.nominomi.lan`| `http://jellyseerr:5055` | `jellyseerr` | `/srv/docker/jellyseerr` | HTTP (`traefik_proxy`) |
| `sonarr.nominomi.lan` | `http://sonarr:8989` | `sonarr` | `/srv/docker/sonarr` | HTTP (`traefik_proxy`) |
| `radarr.nominomi.lan` | `http://radarr:7878` | `radarr` | `/srv/docker/radarr` | HTTP (`traefik_proxy`) |
| `prowlarr.nominomi.lan`| `http://prowlarr:9696` | `prowlarr` | `/srv/docker/prowlarr` | HTTP (`traefik_proxy`) |
| `bazarr.nominomi.lan` | `http://bazarr:6767` | `bazarr` | `/srv/docker/bazarr` | HTTP (`traefik_proxy`) |
| `qbittorrent.nominomi.lan`| `http://qbittorrent:8080`| `qbittorrent` | `/srv/docker/qbittorrent` | HTTP (`traefik_proxy`) |
| `gym.nominomi.lan` | `http://sparkyfitness:80` | `sparkyfitness` | `/srv/docker/sparkyfitness` | HTTP (`traefik_proxy`) |
| `whatomate.nominomi.lan`| `http://whatomate_app:8080` | `whatomate_app` | `/srv/docker/whatomate` | HTTP (`traefik_proxy`) |
| *Cloudflare Tunnel* | `whatomate_app:8080` | `cloudflared` | `/srv/docker/cloudflared` | Outbound tunnel for Meta Webhooks (`traefik_proxy`) |
| *Traefik Dashboard* | `http://127.0.0.1:8080` | `traefik` | `/srv/docker/traefik` | HTTP (`:8080/dashboard/`) |

---

## 3. How Traefik Domain Routing Works

Traefik is configured in `/srv/docker/traefik/compose.yml` with:
- `--providers.file.directory=/etc/traefik`
- `--providers.file.watch=true`
- Volume mount: `/srv/docker/traefik/routes.yml:/etc/traefik/routes.yml:ro`

Because file watching is active, **Traefik automatically detects edits in `routes.yml` within seconds**. You do **not** need to restart or reload the Traefik container after editing `routes.yml`.

### Route Structure in `routes.yml`

Each service needs two blocks in `/srv/docker/traefik/routes.yml`:

#### 1. Router (`http.routers.<name>`)
Defines the incoming request matching rule and assigns it to an entrypoint:
```yaml
http:
  routers:
    myservice:
      rule: "Host(`myservice.nominomi.lan`)"
      entrypoints:
        - web          # Port 80 HTTP (or websecure for Port 443 HTTPS)
      service: myservice
```

#### 2. Service (`http.services.<name>`)
Defines the upstream target server and port:
```yaml
http:
  services:
    myservice:
      loadBalancer:
        servers:
          - url: "http://192.168.1.12:8888"   # Host IP and published container port
```

#### Special Case: Backend Uses HTTPS (Self-Signed)
If the upstream container serves HTTPS (like Portainer on 9443), add `serversTransport`:
```yaml
http:
  serversTransports:
    myservice_transport:
      insecureSkipVerify: true

  routers:
    myservice:
      rule: "Host(`myservice.nominomi.lan`)"
      entrypoints:
        - websecure
      service: myservice
      tls:
        domains:
          - main: "nominomi.lan"

  services:
    myservice:
      loadBalancer:
        servers:
          - url: "https://192.168.1.12:9443"
        serversTransport: myservice_transport
```

---

## 4. Step-by-Step: Adding a New Service

Follow these steps whenever you create a new application in `/srv/docker`.

### Step 1: Choose Name, Port & Domain
1. Choose a short service name (e.g., `dozzle` or `uptime-kuma`).
2. Pick an unused port on `192.168.1.12` (check the registry above or run `ss -tulpn | grep :<PORT>`).
3. Choose the domain (e.g., `logs.nominomi.lan` or `uptime.nominomi.lan`).

### Step 2: Create Service Directory
Create a dedicated folder in `/srv/docker/`:
```bash
mkdir -p /srv/docker/myservice
cd /srv/docker/myservice
```

### Step 3: Write the `compose.yml`
Create `/srv/docker/myservice/compose.yml`. Standard template:

```yaml
services:
  myservice:
    image: vendor/myservice:latest
    container_name: myservice
    restart: unless-stopped
    ports:
      - "8888:80"        # HostPort:ContainerPort
    environment:
      - TZ=Asia/Kolkata
      - PUID=1000
      - PGID=1000
    volumes:
      - /srv/docker/myservice/data:/config
```

> [!TIP]
> If the service needs to communicate directly with media tools (Sonarr, Radarr, qBittorrent), you can attach it to the existing `media` network:
> ```yaml
> networks:
>   default:
>     name: media
>     external: true
> ```

### Step 4: Start the Container
Start the service in detached mode:
```bash
cd /srv/docker/myservice
docker compose up -d
```

Verify that the container is running and healthy:
```bash
docker ps --filter "name=myservice"
docker logs --tail 20 myservice
curl -I http://192.168.1.12:8888
```

### Step 5: Configure Domain Routing in Traefik
Edit `/srv/docker/traefik/routes.yml`:

1. Add router under `http.routers`:
```yaml
    myservice:
      rule: "Host(`myservice.nominomi.lan`)"
      entrypoints:
        - web
      service: myservice
```

2. Add service under `http.services`:
```yaml
    myservice:
      loadBalancer:
        servers:
          - url: "http://192.168.1.12:8888"
```

Save the file. Traefik reloads automatically within 1–2 seconds.

### Step 6: Verify DNS Resolution
Technitium DNS wildcard `*.nominomi.lan` should automatically point to `192.168.1.12`. Verify from the host or client:
```bash
dig @127.0.0.1 -p 53 myservice.nominomi.lan +short
```
If this returns `192.168.1.12`, DNS is ready. If not, open Technitium DNS at `http://dns.nominomi.lan` and add an `A` record or check the wildcard zone.

### Step 7: Test Access
Test routing through Traefik:
```bash
curl -I -H "Host: myservice.nominomi.lan" http://127.0.0.1
```
Open `http://myservice.nominomi.lan` in your browser.

---

## 5. Step-by-Step: Removing an Existing Service

To decommission and cleanly remove a service without leaving orphaned configurations or ports:

### Step 1: Remove Routing from Traefik
1. Open `/srv/docker/traefik/routes.yml`.
2. Locate and delete the router entry for the service under `http.routers`:
   ```yaml
   # Delete this block:
   myservice:
     rule: "Host(`myservice.nominomi.lan`)"
     entrypoints:
       - web
     service: myservice
   ```
3. Locate and delete the service entry under `http.services`:
   ```yaml
   # Delete this block:
   myservice:
     loadBalancer:
       servers:
         - url: "http://192.168.1.12:8888"
   ```
4. Save the file. Traefik drops the route immediately.

### Step 2: Stop and Remove the Docker Container
Navigate to the service folder and bring down the compose stack:
```bash
cd /srv/docker/myservice
docker compose down
```

> [!WARNING]
> If you also want to delete anonymous Docker volumes, use `docker compose down -v`. Do **not** use `-v` if you have mounted host volumes that you want to preserve.

### Step 3: Handle Persistent Data
Decide what to do with the application directory:
- **Retain data / configuration for future use:**
  Leave `/srv/docker/myservice/` as-is, or archive it:
  ```bash
  tar -czvf /srv/docker/myservice-backup.tar.gz -C /srv/docker myservice
  ```
- **Completely purge data:**
  ```bash
  rm -rf /srv/docker/myservice
  ```

### Step 4: Clean Up Unused Docker Images
Remove the container image to free up disk space:
```bash
docker image prune -a
# Or remove the specific image:
docker rmi vendor/myservice:latest
```

---

## 6. Alternative Routing Method: Docker Labels

In addition to `routes.yml` (File Provider), Traefik has `--providers.docker=true` enabled. If you prefer to declare routes directly inside the service's `compose.yml` instead of modifying `routes.yml`:

1. Attach the service to the `traefik_default` Docker network.
2. Add Traefik labels in `compose.yml`:

```yaml
services:
  myservice:
    image: vendor/myservice:latest
    container_name: myservice
    restart: unless-stopped
    networks:
      - traefik_default
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myservice.rule=Host(`myservice.nominomi.lan`)"
      - "traefik.http.routers.myservice.entrypoints=web"
      - "traefik.http.services.myservice.loadbalancer.server.port=80"

networks:
  traefik_default:
    external: true
```

### File Provider (`routes.yml`) vs Docker Provider (Labels)

| Feature | File Provider (`routes.yml`) [Current Setup] | Docker Labels Provider |
| :--- | :--- | :--- |
| **Network Isolation** | Containers can use any network (`bridge`, `host`, `media`). Traefik routes via published host IP `192.168.1.12`. | Containers must join `traefik_default` network so Traefik can reach container IPs directly. |
| **Centralization** | All domain mappings are listed in one single file. Easy to audit all routes in one glance. | Routes are scattered across separate `compose.yml` files. |
| **Non-Docker Services**| Can route to services running outside Docker or on host network (e.g., CasaOS, Technitium). | Only works for Docker containers running on Docker socket. |

**Recommendation:** Continue using `routes.yml` for unified routing across CasaOS, host-networked apps, and Docker containers.

---

## 7. Maintenance & Troubleshooting Playbook

### Diagnostic Commands Quick Reference

| Action | Command |
| :--- | :--- |
| **Check Traefik Logs** | `docker logs -f --tail 50 traefik` |
| **Check Listening Ports** | `ss -tulpn \| grep LISTEN` |
| **Check Port in Use** | `ss -tulpn \| grep :<PORT>` |
| **Test Hostname via Traefik** | `curl -I -H "Host: <app>.nominomi.lan" http://127.0.0.1` |
| **Test Direct Backend Port** | `curl -I http://192.168.1.12:<PORT>` |
| **Test Local DNS Query** | `dig @127.0.0.1 -p 53 <app>.nominomi.lan +short` |
| **Restart Traefik** | `cd /srv/docker/traefik && docker compose restart` |

### Common Issues & Solutions

#### 1. `404 Not Found` when opening `app.nominomi.lan`
- **Cause 1:** Host header does not match the `rule: "Host(...)` in `routes.yml`. Check for typos.
- **Cause 2:** Route was not saved properly or has YAML indentation errors.
- **Verification:** Run `docker logs traefik | grep -i error` to see if Traefik rejected `routes.yml`.

#### 2. `502 Bad Gateway`
- **Cause:** Traefik received the request, but the target upstream service at `http://192.168.1.12:<PORT>` is either stopped or not responding.
- **Fix:**
  1. Check if the container is running: `docker ps | grep <app>`.
  2. Verify the backend port responds: `curl http://192.168.1.12:<PORT>`.
  3. Ensure the port number in `routes.yml` matches the published host port in the application's `compose.yml`.

#### 3. `bind: address already in use` when starting a container
- **Cause:** Another container or host process is already listening on that port.
- **Fix:** Find the conflicting process using `sudo ss -tulpn | grep :<PORT>` and choose a different host port in `compose.yml` and `routes.yml`.

#### 4. Browser cannot reach `*.nominomi.lan` (`DNS_PROBE_FINISHED_NXDOMAIN`)
- **Cause:** Client device is not using the Technitium DNS server (`192.168.1.12`).
- **Fix:** Ensure router DHCP or client network settings specify `192.168.1.12` as primary DNS server.

---
*Maintained by Server Administrator. Last updated: November 2026.*
