# Deploy · Gathering demo on the homelab cluster

URL: https://cs2207.datrollout.dev/trajectory/gathering (`/` redirects there).
Image: `ghcr.io/uitprojects/cs2207-gathering-demo:1.0` (build/push steps in `../README.md`).

| File | What |
|---|---|
| `00-namespace.yaml` | namespace `cs2207` |
| `10-deployment.yaml` | Streamlit pod, served under `/trajectory/gathering` via `STREAMLIT_SERVER_BASE_URL_PATH` |
| `20-service.yaml` | ClusterIP `gathering-demo:80` → 8501 |
| `30-middleware.yaml` | Traefik redirect `/` → `/trajectory/gathering/` |
| `40-ingress.yaml` | Traefik ingresses (websecure, Let's Encrypt resolver, CrowdSec) |

## Apply

```bash
kubectl apply -f deploy/
kubectl -n cs2207 rollout status deploy/gathering-demo
curl -I https://cs2207.datrollout.dev/          # 302 → /trajectory/gathering/
```

DNS: `cs2207.datrollout.dev` must point at Traefik like the other `*.datrollout.dev` hosts.

## If the GHCR package is private

Make it public (UITProjects org → Packages → cs2207-gathering-demo → Package settings → Change visibility), or create a pull secret
with a token that has `read:packages` and uncomment `imagePullSecrets` in `10-deployment.yaml`:

```bash
kubectl -n cs2207 create secret docker-registry ghcr-pull \
  --docker-server=ghcr.io --docker-username=<github-username> --docker-password="$GHCR_TOKEN"
```

## Update to a new image

Push a new tag (e.g. `1.1`), then:

```bash
kubectl -n cs2207 set image deploy/gathering-demo app=ghcr.io/uitprojects/cs2207-gathering-demo:1.1
```
