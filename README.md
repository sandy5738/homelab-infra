# Homelab Infrastructure Monorepo (`homelab-infra`)

This repository contains the complete Infrastructure-as-Code (IaC), reverse-proxy routing, and Ansible automations for the homelab server.

---

## Repository Structure

```text
homelab-infra/
├── srv/                             # Everything deployed to /srv on target nodes
│   ├── docker/                      # Production Docker Compose stacks
│   │   ├── traefik/                 # Ingress proxy + Socket Proxy (ADR-005)
│   │   ├── adguard/                 # Wildcard DNS & AdBlocking (ADR-006)
│   │   ├── cloudflared/             # Cloudflare Tunnel (whatomate.nominomi.cloud)
│   │   ├── jellyfin-nvidia/         # Media server with GPU transcoding
│   │   ├── jellyseerr/              # Media request portal
│   │   ├── sonarr/                  # TV automation
│   │   ├── radarr/                  # Movie automation
│   │   ├── prowlarr/                # Indexer proxy
│   │   ├── bazarr/                  # Subtitle management
│   │   ├── qbittorrent/             # Torrent downloader
│   │   ├── sparkyfitness/           # Fitness & workout tracker
│   │   ├── whatomate/               # WhatsApp Cloud API automation
│   │   ├── glance/                  # Unified homelab dashboard
│   │   ├── assistant/               # Home Assistant automation
│   │   └── portainer/               # Container management UI
│   ├── ADR.md                       # Architecture Decision Records (ADR-001 - ADR-006)
│   └── CLEANUP.md                   # Modernization audit and checklist
├── ansible/                         # Infrastructure automation playbooks
│   ├── ansible.cfg                  # Ansible configuration defaults
│   ├── inventory.ini.example        # Host inventory template (gitignored)
│   └── playbooks/
│       ├── 01-bootstrap.yml         # Server OS, Docker, kernel, and storage setup
│       └── 02-deploy.yml            # Syncs srv/ to target /srv and restarts stacks
├── k8s/                             # Future Kubernetes (K3s) migration manifests
│   └── README.md                    # Kubernetes migration guide and storage layout
├── .gitignore                       # Strict exclusion for secrets, certs, and data
└── README.md                        # This documentation
```

---

## Deploying with Ansible

### 0. Prepare Inventory
Copy the template and configure your server IP and credentials:
```bash
cp ansible/inventory.ini.example ansible/inventory.ini
nano ansible/inventory.ini
```

### 1. Bootstrap Server (New Machine / Disaster Recovery)
Installs Docker, creates users, sets up UFW, and creates the `traefik_proxy` bridge:
```bash
ansible-playbook -i ansible/inventory.ini ansible/playbooks/01-bootstrap.yml
```

### 2. Deploy or Update Stacks
Syncs the `srv/` directory and restarts the Docker containers:
```bash
ansible-playbook -i ansible/inventory.ini ansible/playbooks/02-deploy.yml
```

---

## DNS & Ingress Topology

* **Private Domain:** `*.nominomi.lan`
* **Local DNS:** AdGuard Home (`http://dns.nominomi.lan`) with wildcard rewrite `*.nominomi.lan -> 192.168.1.12`
* **Public Domain:** `whatomate.nominomi.cloud` (via Cloudflare Zero Trust Tunnel)
* **Security:** Docker Socket Proxy (`tecnativa/docker-socket-proxy`) with read-only `POST=0` privilege isolation.
