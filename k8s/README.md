# Kubernetes (K8s / K3s) Architecture & Migration Plan

This directory documents the planned evolution of this homelab from Docker Compose to a lightweight, production-grade Kubernetes cluster using **K3s** or **Talos Linux**.

---

## Architecture Mapping: Docker Compose vs. Kubernetes

| Component | Docker Compose (`/srv/docker`) | Kubernetes Equivalent (`k8s/`) |
| :--- | :--- | :--- |
| **Ingress Proxy** | Traefik v3 (`traefik/compose.yml`) | Traefik Kubernetes Ingress Controller (built-in to K3s) |
| **DNS & AdBlocking** | AdGuard Home (`adguard/compose.yml`) | CoreDNS + AdGuard Home / Blocky |
| **Routing Rules** | Traefik File Provider (`routes.yml`) | Kubernetes `Ingress` or Traefik `IngressRoute` CRDs |
| **Socket Security** | `tecnativa/docker-socket-proxy` | Kubernetes RBAC ServiceAccounts (least-privilege) |
| **Persistent Volumes**| Bind mounts (`./data:/app/data`) | `PersistentVolumeClaim` (PVC) using `local-path-provisioner` (`/srv/k8s/data`) |
| **Secrets** | `.env` files + `.gitignore` | SOPS / SealedSecrets / External Secrets Operator (ESO) |
| **GitOps Engine** | Ansible `02-deploy.yml` | **ArgoCD** or **FluxCD** syncing from this repo |

---

## Storage Strategy for Kubernetes (`/srv/k8s`)

In single-node or local clusters, persistent state will live under `/srv/k8s/`:
* `/srv/k8s/storage/`: Managed by Rancher `local-path-provisioner` CSI driver.
* `/mnt/SandysHDD/Media`: Mounted into pods via a static `PersistentVolume` (PV) with `hostPath: /mnt/SandysHDD/Media`.

---

## Migration Steps via Kompose

Compose stacks can be translated directly into Kubernetes manifests:
```bash
# Convert a compose stack to Kubernetes manifests:
kompose convert -f /srv/docker/sonarr/compose.yml -o k8s/apps/media/sonarr/
```
