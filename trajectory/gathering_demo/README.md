# Gathering demo · buổi hòa nhạc (CS2207 · Nhóm 12)

Streamlit app for the Gathering pattern (K. Zheng et al., "On Discovery of Gathering Patterns from Trajectories", ICDE 2013).
A fake concert dataset (400 points, t₁…t₁₀ = 19:00 → 20:30, every 10 min) goes through the full pipeline:
DBSCAN snapshot clusters → closed crowds (Algorithm 1, Hausdorff ≤ δ) → Test-and-Divide (bit vectors).

| File | Role |
|---|---|
| `app.py` | Streamlit UI (steps 0–4, 3D x–y–t plot, 2D route map) |
| `gathering_core.py` | dataset generator (fixed seed) + pipeline, no Streamlit |
| `check_core.py` | asserts the expected crowds and gatherings; also runs during `docker build` |
| `.streamlit/config.toml` | theme |

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Docker → GitHub Container Registry

Image: `ghcr.io/uitprojects/cs2207-gathering-demo` (GHCR names must be lowercase).

Build (from this folder):

```bash
docker build -t ghcr.io/uitprojects/cs2207-gathering-demo:1.0 -t ghcr.io/uitprojects/cs2207-gathering-demo:latest --label org.opencontainers.image.source=https://github.com/UITProjects/cs2207 .
```

Log in with a GitHub personal access token (classic) that has `write:packages`:

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-username> --password-stdin
```

Push:

```bash
docker push ghcr.io/uitprojects/cs2207-gathering-demo:1.0
```

```bash
docker push ghcr.io/uitprojects/cs2207-gathering-demo:latest
```

A new package on GHCR is private. To pull it without logging in, set it to public under the org's *Packages* settings.

## Run the container

Create the network once:

```bash
docker network create cs2207-net
```

Run on that network and publish port 8501:

```bash
docker run -d --name gathering-demo --network cs2207-net -p 8501:8501 --restart unless-stopped ghcr.io/uitprojects/cs2207-gathering-demo:latest
```

Open http://localhost:8501. Other containers on `cs2207-net` (for example a reverse proxy) reach it at `http://gathering-demo:8501`.

On a Linux host you can use the host network instead (no `-p` needed):

```bash
docker run -d --name gathering-demo --network host ghcr.io/uitprojects/cs2207-gathering-demo:latest
```
