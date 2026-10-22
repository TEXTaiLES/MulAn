# MulAn

MulAn is the TEXTaiLES tool for converting ordered grayscale and RGB BMP channels into multiband TIFFs, inspecting multispectral TIFF channels, and creating ML-ready semantic-segmentation masks. The canonical mask is one integer TIFF band in source-image coordinates; changing the displayed spectral channel never changes annotations.

MulAn runs on top of HESTIA: users sign in on the HESTIA portal, and images and annotations are read from and saved to HESTIA's MulAn endpoints (`/api/v1/multispectral/images…`). MulAn keeps no accounts or data of its own.

## Run with Docker

Requirements: Docker Engine with Docker Compose, and a running HESTIA (API and portal).

```bash
docker compose up --build
```

Open <http://localhost:5001> (or the port set by `MULAN_PORT`). Signed-out users are sent to the HESTIA portal and come back to MulAn's front page after signing in. The one application service builds the React UI, serves it from Flask/Gunicorn, and keeps its working files (cached HESTIA images and annotation working copies) in the `mulan-data` volume. Stop with `docker compose down`; add `-v` only when you intentionally want to remove those working files.

Optional settings can be placed in `.env` (see `.env.example`):

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MULAN_PORT` | `5001` | Port the application listens on, in Docker and in local development (Flask dev server, Vite proxy, Playwright). HESTIA's API uses 5000, and HESTIA's default `MULAN_ORIGINS` is `http://localhost:5001` |
| `MULAN_DATA_DIR` | `./data` locally, `/data` in Docker | Cached HESTIA images, previews, annotation working copies, and undo history |
| `MULAN_RESOURCE_TTL_HOURS` | `24` | Age after which working files are eligible for startup/manual cleanup |
| `MULAN_MAX_UPLOAD_MB` | `512` | Maximum request size |
| `HESTIA_API_URL` | `http://localhost:5000` (`http://host.docker.internal:5000` in Docker) | HESTIA API, called by MulAn's backend |
| `HESTIA_PORTAL_URL` | `http://localhost:8055` | HESTIA portal that the browser is sent to for sign-in and sign-out |
| `HESTIA_COOKIE_NAME` | `textailes_refresh_token` | HESTIA session cookie that MulAn forwards to HESTIA |
| `HESTIA_TIMEOUT_SECONDS` | `30` | Timeout for each HESTIA call |
| `MULAN_PUBLIC_URL` | derived from the request | MulAn's public URL, used as the post-login redirect |

## Local development

Requirements: Python 3.12, npm, and a supported Node.js release (20.19+, 22.12+, or a newer LTS).

Backend (macOS/Linux):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m mulan
```

Backend (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m mulan
```

The editable install maps the `mulan` package from `backend/`. In a second terminal, run the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/auth` requests to Flask on `MULAN_PORT`.

Use `localhost`, not `127.0.0.1`, in the browser: the HESTIA portal sets its session cookie for `localhost`, and browsers share it across ports, so MulAn receives it.

## Tests and production build

```bash
# repository root: backend
python -m pytest

# frontend
cd frontend
npm test
npm run build

# critical browser workflows against a running HESTIA (install once, then run)
npx playwright install chromium
MULAN_E2E_HESTIA_TOKEN=<textailes_refresh_token cookie value> npm run e2e
```

Backend tests use an in-memory fake of HESTIA's MulAn endpoints (`tests/backend/fake_hestia.py`). Playwright starts the Flask and Vite development servers and skips the workflows unless `MULAN_E2E_HESTIA_TOKEN` holds a HESTIA session token; copy it from the `textailes_refresh_token` cookie after signing in on the portal. If your platform uses a versioned Python command, start Flask manually with `python -m mulan` first; Playwright reuses a running server.

## How it is organized

- `backend/mulan/auth.py`: HESTIA sign-in redirects and the cached HESTIA session (user and capabilities).
- `backend/mulan/hestia.py`: HTTP client for HESTIA's MulAn endpoints.
- `backend/mulan/api`: stable `/api/v1` and UI-only `/api/internal/v1` HTTP adapters.
- `backend/mulan/services`: TIFF/BMP processing, previews, canonical masks, raster operations, history, and export; `hestia_images.py` caches HESTIA images locally and `hestia_annotations.py` opens and saves annotation working copies.
- `backend/mulan/storage`: UUID-scoped filesystem storage for working files and TTL cleanup.
- `frontend/src`: React pages, shared controls, API client, and the tested source/display coordinate transform.
- `tests/backend`, `frontend/src/**/*.test.*`, `e2e`: synthetic backend, component, and critical workflow tests.

Image sources are stored unchanged. Previews are disposable normalized PNGs. Annotation operations are sent in source pixel coordinates and mutate a server-side `uint16` canonical mask using bounded reversible region patches. Export selects `uint8` when all class IDs fit and `uint16` otherwise. Source CRS and affine transform are copied to masks only when the source is georeferenced.

## Usage

1. **Convert:** add grayscale and/or RGB BMP files, arrange the file groups from lower to higher wavelength using the on-screen guide, optionally name the expanded bands, convert (the TIFF is saved to HESTIA as a new image), and download the TIFF. Evident grayscale filenames such as `700.bmp`, `700nm.bmp`, or `wavelength_700.bmp` initialize an editable `700nm` channel name. Grayscale contributes one band; RGB contributes grouped `R`, `G`, `B` bands without changing pixel values.
2. **Viewer:** pick a HESTIA image (or upload a TIFF to HESTIA), move between single channels or a thumbnail grid, zoom/pan, and open the same `image_id` in Annotator.
3. **Annotator:** create stable-ID classes; use `H` for pan, `B` for brush, `E` for eraser, `L`/`Shift+L` for lasso add/subtract, and `R`/`Shift+R` for rectangle add/subtract; change spectral channels without changing the mask; undo/redo drawing and applied masks with the toolbar or `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, and `Ctrl/Cmd+Y`; optionally replace the mask after confirmation; save to HESTIA and export HESTIA's mask package with or without the original image. Opening an image loads its saved HESTIA annotation into a working copy; if someone else saves a newer version first, MulAn refuses to overwrite it and offers to reload.

The standalone API is documented in [API.md](API.md).

## Permissions

MulAn follows the capabilities HESTIA reports for the signed-in user (from HESTIA's Directus role permissions): `images_read` to list, view, and preview images; `images_create` to upload or convert images; `annotations_read` to open the Annotator; `annotations_create` for the first save of an image's annotation and `annotations_update` for later saves. HESTIA enforces each of these on every call; MulAn hides or disables what the user cannot do.

## MulAn v1 limitations

MulAn's own files are temporary working copies; HESTIA is the source of truth. HESTIA has no endpoints to delete images or annotations, so MulAn offers neither. Collaboration is limited to HESTIA's revision check on save. There is no dataset management, inference, instance segmentation, mask merging, reprojection, or CRS editing. TIFF support is limited to ordinary raster datasets Rasterio exposes as one or more bands; OME/hyperstack semantics and exotic page layouts are not interpreted. The annotator is desktop-first.
