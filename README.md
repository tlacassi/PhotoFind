# PhotoFind

A photographer shares a gallery by link or QR code, and the client finds their own photos
with a selfie. A vibe-coded experiment to test the concept.

## How it works

1. The photographer creates a gallery and drops photos into it.
2. The server detects and matches faces with OpenCV (YuNet, SFace).
   Nothing is sent to an external recognition service.
3. The client opens a private link (valid 1 to 90 days), no account needed.
4. They take a selfie and get the photos where they appear. The selfie is not kept.

Also: photographer accounts, shared galleries, per-gallery branding, storage quotas.

Python, FastAPI, SQLite, Docker.

## Run locally

```sh
docker compose -f compose.local.yaml build
docker compose -f compose.local.yaml run --rm photofind python create_admin.py
docker compose -f compose.local.yaml up -d
```

Then open <http://127.0.0.1:8000>.

Prototype. The interface is in French.

[Detailed notes (in French)](docs/README.fr.md)
