# MulAn

MulAn is a single-user web application for converting ordered grayscale and RGB BMP channels into multiband TIFFs, inspecting multispectral TIFF channels, and creating ML-ready semantic-segmentation masks. The canonical mask is one integer TIFF band in source-image coordinates; changing the displayed spectral channel never changes annotations.

## Run with Docker

Requirements: Docker Engine with Docker Compose.

```bash
docker compose up --build
```

Open <http://localhost:5000>. The one application service builds the React UI, serves it from Flask/Gunicorn, and stores temporary resources in the `mulan-data` volume. Stop with `docker compose down`; add `-v` only when you intentionally want to remove stored temporary resources.

Optional settings can be placed in `.env` (see `.env.example`):

| Variable | Default | Purpose |
| --- | ---: | --- |
| `MULAN_DATA_DIR` | `./data` locally, `/data` in Docker | Image, annotation, preview, and history storage |
| `MULAN_RESOURCE_TTL_HOURS` | `24` | Age after which resources are eligible for startup/manual cleanup |
| `MULAN_MAX_UPLOAD_MB` | `512` | Maximum request size |

## Local development

Requirements: Python 3.12, npm, and a supported Node.js release (20.19+, 22.12+, or a newer LTS).

Backend (macOS/Linux):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m flask --app mulan.wsgi run --debug --port 5000
```

Backend (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m flask --app mulan.wsgi run --debug --port 5000
```

The editable install maps the `mulan` package from `backend/`. In a second terminal, run the frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` requests to Flask on port 5000.

## Tests and production build

```bash
# repository root: backend
python -m pytest

# frontend
cd frontend
npm test
npm run build

# critical browser workflows (install once, then run)
npx playwright install chromium
npm run e2e
```

Playwright starts the Flask and Vite development servers. If your platform uses a versioned Python command, start Flask manually on port 5000 first; Playwright reuses a running server.

## How it is organized

- `backend/mulan/api`: stable `/api/v1` and UI-only `/api/internal/v1` HTTP adapters.
- `backend/mulan/services`: TIFF/BMP processing, previews, canonical masks, raster operations, history, and export.
- `backend/mulan/storage`: UUID-scoped filesystem storage and TTL cleanup.
- `frontend/src`: React pages, shared controls, API client, and the tested source/display coordinate transform.
- `tests/backend`, `frontend/src/**/*.test.*`, `e2e`: synthetic backend, component, and critical workflow tests.

Image sources are stored unchanged. Previews are disposable normalized PNGs. Annotation operations are sent in source pixel coordinates and mutate a server-side `uint16` canonical mask using bounded reversible region patches. Export selects `uint8` when all class IDs fit and `uint16` otherwise. Source CRS and affine transform are copied to masks only when the source is georeferenced.

## Usage

1. **Convert:** add grayscale and/or RGB BMP files, arrange the file groups from lower to higher wavelength using the on-screen guide, optionally name the expanded bands, convert, and download the TIFF. Evident grayscale filenames such as `700.bmp`, `700nm.bmp`, or `wavelength_700.bmp` initialize an editable `700nm` channel name. Grayscale contributes one band; RGB contributes grouped `R`, `G`, `B` bands without changing pixel values.
2. **Viewer:** upload a TIFF, move between single channels or a thumbnail grid, zoom/pan, and open the same `image_id` in Annotator.
3. **Annotator:** create stable-ID classes; use `H` for pan, `B` for brush, `E` for eraser, `L`/`Shift+L` for lasso add/subtract, and `R`/`Shift+R` for rectangle add/subtract; change spectral channels without changing the mask; undo/redo drawing and applied masks with the toolbar or `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`, and `Ctrl/Cmd+Y`; optionally replace the mask after confirmation; save and export the mask package with or without the original image.

The standalone API is documented in [API.md](API.md).

## MulAn v1 limitations

Resources are temporary and filesystem-backed. There are no accounts, authentication, collaboration, persistent libraries, cloud storage, dataset management, inference, instance segmentation, mask merging, reprojection, or CRS editing. TIFF support is limited to ordinary raster datasets Rasterio exposes as one or more bands; OME/hyperstack semantics and exotic page layouts are not interpreted. The annotator is desktop-first.
