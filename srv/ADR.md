# Architecture Decision Records (ADR)

This document records the architectural decisions made for the homelab infrastructure on `enma` (`192.168.1.12`). Each record follows the Michael Nygard format, detailing context, decisions, rationale, and consequences to provide long-term auditability and maintainability.

---

## Index of Decisions

1. [ADR-001: Decommissioning CasaOS & Adopting Modular Compose Stacks](#adr-001-decommissioning-casaos--adopting-modular-compose-stacks)
2. [ADR-002: Network Hardening & Host Port Elimination via `traefik_proxy`](#adr-002-network-hardening--host-port-elimination-via-traefik_proxy)
3. [ADR-003: Domain Transition from Multicast DNS (`.local`) to Private Unicast DNS (`.lan`)](#adr-003-domain-transition-from-multicast-dns-local-to-private-unicast-dns-lan)
4. [ADR-004: Decoupling Storage & System Paths via Environment Variables (`.env`)](#adr-004-decoupling-storage--system-paths-via-environment-variables-env)

---

## ADR-001: Decommissioning CasaOS & Adopting Modular Compose Stacks

* **Date:** 2026-11-20
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
The server historically ran CasaOS as an application manager. CasaOS introduced significant technical debt:
1. Container definitions contained proprietary `x-casaos:` metadata.
2. Configuration files and persistent databases were split between `/DATA/AppData/`, `/data/compose/`, and `/srv/docker/`.
3. CasaOS isolated containers across arbitrary default bridge networks, causing inter-service communication failures (e.g. Sonarr unable to resolve `qbittorrent`).
4. High risk of configuration drift between CasaOS GUI edits and raw CLI edits, preventing declarative GitOps.

### Decision
1. Take a cold pre-migration backup of all application data to `/srv/backup-pre-migration/`.
2. Migrate all application states (Radarr, Sonarr, Prowlarr, qBittorrent, Jellyfin, Jellyseerr, Home Assistant) into standardized standalone directories under `/srv/docker/<app>/data/`.
3. Standardize compose files in `/srv/docker/<app>/compose.yml`, stripping all CasaOS tags.
4. Unify media services under a shared Docker bridge network (`media`).
5. Remove CasaOS root directories (`/DATA`, `/data`) from the filesystem.

### Consequences
* **Positive:**
  * Zero data loss achieved; all SQLite databases, torrent configs, and Jellyfin libraries were preserved intact.
  * Sonarr, Radarr, Prowlarr, and qBittorrent communicate natively via container DNS (`http://qbittorrent:8080`).
  * Stacks are fully modular and independent of any GUI vendor.
* **Negative / Trade-off:**
  * Systemd units for CasaOS daemons remain installed until explicitly disabled by user via sudo (`sudo systemctl disable --now casaos*`).

---

## ADR-002: Network Hardening & Host Port Elimination via `traefik_proxy`

* **Date:** 2026-11-20
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
Containers previously published raw ports (`0.0.0.0:<PORT>`) to the host network (e.g., Sonarr on `8989`, Radarr on `7878`, qBittorrent on `8181`). This presented major security risks:
1. Any device on the LAN could browse directly to `http://192.168.1.12:8989`, bypassing Traefik routing, TLS encryption, and future authentication middleware.
2. Traefik was configured using host loopback URLs (`http://192.168.1.12:<PORT>`) rather than container-native DNS.

### Decision
1. Create a dedicated external bridge network: `docker network create traefik_proxy`.
2. Attach Traefik and all web service frontends to `traefik_proxy`.
3. Remove published host `ports:` bindings from all service compose files. Only Traefik exposes web ports `80` and `443` on the host.
4. Keep UDP discovery ports `7359:7359/udp` and `1901:1900/udp` on Jellyfin for smart TV auto-discovery.
5. In Traefik [routes.yml](file:///srv/docker/traefik/routes.yml), route all reverse proxy traffic directly to internal container DNS names and internal ports (e.g. `http://sonarr:8989`, `http://qbittorrent:8080`).
6. Update inter-service database configs (Radarr -> qBittorrent & Prowlarr; Jellyseerr -> Jellyfin; Bazarr -> Sonarr & Radarr) to use internal Docker DNS.
7. Configure Home Assistant `configuration.yaml` with `use_x_forwarded_for: true` and `trusted_proxies: [172.16.0.0/12]` to accept reverse-proxied traffic from Traefik.

### Consequences
* **Positive:**
  * Perimeter is fully hardened. Web traffic cannot bypass Traefik.
  * Internal inter-service traffic stays inside isolated bridge networks (`media` and `traefik_proxy`).
  * Single point of ingress simplifies certificate management and authentication.
* **Negative / Trade-off:**
  * Containers with `network_mode: host` (Home Assistant, Technitium) cannot join bridge networks and must be reached by Traefik via host IP.

---

## ADR-003: Domain Transition from Multicast DNS (`.local`) to Private Unicast DNS (`.lan`)

* **Date:** 2026-11-20
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
The homelab historically resolved services using `*.nominomi.local`. 
1. **RFC 6762:** Strictly reserves `.local` for Multicast DNS (mDNS).
2. **Conflict:** The host runs `avahi-daemon` (broadcasting `enma.local`). Client OS resolvers (macOS Bonjour, iOS, Windows mDNS, Linux systemd-resolved) intercept any query ending in `.local` and broadcast UDP queries to `224.0.0.251:5353` instead of querying the unicast DNS server (Technitium on port 53).
3. This caused intermittent DNS resolution failures, slow lookups, and timeouts on client devices.

### Decision
1. Transition the homelab domain from `*.nominomi.local` to `*.nominomi.lan`.
2. In Technitium DNS, create a Primary Zone `nominomi.lan` with wildcard record `*.nominomi.lan -> 192.168.1.12`.
3. Generate a new wildcard TLS certificate for `nominomi.lan` (`/srv/docker/traefik/certs/nominomi.lan.crt` & `.key`) with Subject Alternative Names (SANs).
4. Update Traefik routing rules in [routes.yml](file:///srv/docker/traefik/routes.yml) to match `Host(*.nominomi.lan)`.
5. Update application environment variables (e.g. `SPARKY_FITNESS_FRONTEND_URL=http://gym.nominomi.lan`).

### Consequences
* **Positive:**
  * Completely eliminates mDNS collisions with Avahi and client operating systems.
  * Unicast DNS queries resolve reliably without timeouts.
  * Retains clean `.lan` naming for all local homelab services.
* **Negative / Trade-off:**
  * Browser bookmarks and client DNS entries must be updated from `.local` to `.lan`.

---

## ADR-004: Decoupling Storage & System Paths via Environment Variables (`.env`)

* **Date:** 2026-11-20
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
Previous compose files hardcoded host-specific paths directly into volume mounts:
* `/mnt/SandysHDD/Media` hardcoded in Sonarr, Radarr, qBittorrent, Bazarr, and Jellyfin.
* `/var/run/docker.sock` hardcoded in Traefik and Portainer.
* `./data` hardcoded without fallback parameterization.
This created strong coupling to the host environment, made drive remounting or disk migration difficult, and exposed host filesystem details in version control.

### Decision
1. Parameterize all volume definitions across compose files using Docker Compose parameter expansion with sensible defaults:
   * `${MEDIA_DIR:-/mnt/SandysHDD/Media}`
   * `${DATA_DIR:-./data}`
   * `${DOCKER_SOCK:-/var/run/docker.sock}`
2. Provide a `.env` file in each application directory specifying default values.
3. Provide a global reference template at `/srv/docker/.env.example`.

### Consequences
* **Positive:**
  * Compose files are 100% portable and infrastructure-agnostic.
  * Migrating a media drive mount point only requires changing `MEDIA_DIR` in `.env` rather than modifying multiple YAML files.
  * Compose files can be safely committed to Git without exposing private host paths.
* **Negative / Trade-off:**
  * Requires managing `.env` files alongside compose files.

---

## ADR-005: Docker Socket Proxy Isolation & Traefik Dashboard Hardening

* **Date:** 2026-11-23
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
Traefik previously mounted `/var/run/docker.sock` directly with read-only root host access and exposed its dashboard and API publicly on `0.0.0.0:8080` with `--api.insecure=true`. This presented two major security risks:
1. Direct Docker socket access allows container escape or host compromise if the ingress proxy is exploited.
2. An unauthenticated dashboard on `:8080` exposed container topology, internal network addresses, and metrics to any device on the local network.

### Decision
1. Deploy `tecnativa/docker-socket-proxy:latest` (`docker_socket_proxy`) on the internal `traefik_proxy` network with strict least-privilege permissions:
   * Enabled read-only flags: `CONTAINERS=1`, `NETWORKS=1`, `SERVICES=1`, `VERSION=1`, `INFO=1`.
   * Enforced write block: `POST=0` (disallowing container creation, execution, deletion, or socket hijacking).
2. Remove the `/var/run/docker.sock` host mount from the `traefik` container. Configure Traefik to query `--providers.docker.endpoint=tcp://docker_socket_proxy:2375`.
3. Remove raw host port `8080:8080` and disable `--api.insecure=true`.
4. Route the Traefik dashboard internally through Traefik itself via `api@internal` on `traefik.nominomi.lan` (both HTTP and HTTPS), protected by Traefik BasicAuth middleware (`traefik-auth`) using Bcrypt password hashing.

### Consequences
* **Positive:**
  * Traefik has zero direct access to the host Docker daemon socket.
  * Ingress breach cannot escalate to host root access or container execution.
  * Dashboard port `:8080` is closed on the LAN; access requires valid HTTP BasicAuth credentials over HTTPS.
* **Negative / Trade-off:**
  * Traefik dashboard now prompts for BasicAuth login credentials.

---

## ADR-006: Migration from Technitium DNS to AdGuard Home

* **Date:** 2026-11-23
* **Status:** Accepted & Implemented
* **Deciders:** Server Admin & Antigravity

### Context
Technitium DNS was initially deployed solely to provide a wildcard rewrite for `*.nominomi.lan`. While functional, Technitium runs on a heavy .NET runtime (~150-250MB RAM), accumulated dozens of megabytes of daily binary statistics files, required host-network mode, and maintained an external host port `5380`.

### Decision
1. Replace Technitium with `adguard/adguardhome:latest` deployed in `/srv/docker/adguard/`.
2. Connect AdGuard Home to the internal `traefik_proxy` bridge network, routing `http://dns.nominomi.lan` and `https://dns.nominomi.lan` via Traefik to `http://adguard:3000`.
3. Configure native AdGuard wildcard DNS rewrites for `*.nominomi.lan` and `nominomi.lan` pointing to `192.168.1.12`.
4. Decommission and remove the Technitium container and configuration.

### Consequences
* **Positive:**
  * Ultra-lightweight Go binary: memory usage dropped to ~44MB RAM.
  * Native ad-blocking and tracking protection for all LAN devices.
  * Clean, single-pane web dashboard accessible at `dns.nominomi.lan`.
  * Single wildcard rule covers all present and future `.nominomi.lan` services.
* **Negative / Trade-off:**
  * Requires managing AdGuard Home web credentials.
