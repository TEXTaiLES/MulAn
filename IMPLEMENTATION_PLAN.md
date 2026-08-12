# MulAn Implementation Plan

## Summary

Build a single-service Flask + React/Vite application for BMP-to-multiband-TIFF conversion, multispectral TIFF viewing, and semantic-mask annotation. Store temporary resources on the local filesystem under `MULAN_DATA_DIR`; serve the production SPA and API from Gunicorn in one Docker Compose service.

## Dependency choices and layout

- Backend: Python 3.12, Flask, Rasterio, NumPy, Pillow, Gunicorn, pytest; use `pyproject.toml`.
- Frontend: React, TypeScript, Vite, React Router, Konva/react-konva, dnd-kit, lucide-react, Vitest, React Testing Library, Playwright; configure Vite API proxy to `localhost:5000`.
- Create:
  - `backend/mulan/{api,services,storage,models,static}`
  - `frontend/src/{pages,components,features,api,utils}`
  - `tests/backend`, `frontend/src/**/*.test.tsx`, `e2e`
  - root `Dockerfile`, `compose.yaml`, `.env.example`, `README.md`, `API.md`, and `IMPLEMENTATION_PLAN.md`.
- Use UUID-scoped directories for images and annotations; persist small metadata and history patches as JSON/files. Configure TTL cleanup and upload limits via environment variables.

## Milestones

1. **Foundation**
   - Scaffold Flask application factory, typed configuration, JSON error handling, API blueprints, filesystem storage abstraction, cleanup service, health/static SPA serving, and development proxy.
   - Add Docker multi-stage frontend build plus a persistent data volume.
   - Define shared image/annotation metadata models and stable `/api/v1` response/error contracts.

2. **Image resources and conversion**
   - Implement TIFF upload, metadata, unchanged original download, deletion safety, cached percentile-normalized PNG channel previews, and metadata preservation.
   - Implement one BMP conversion service used by both direct-download and resource modes.
   - Validate ordered grayscale BMP inputs, RGB equality before accepting RGB-encoded grayscale data, matching dimensions/dtype, channel names, filenames, and manifest fields.
   - Write one-band-per-input TIFFs with Rasterio band descriptions and no invented geospatial metadata.

3. **Annotation backend**
   - Implement annotation creation from upload or existing `image_id`, canonical single-band integer mask storage, class CRUD, import/replace validation, mask retrieval, ZIP export, and annotation deletion.
   - Preserve source CRS/transform in exported masks when present; choose `uint8` or `uint16` export dtype based on maximum class ID.
   - Add internal operation, overlay, undo, redo, and save endpoints. Store bounded reversible changed-region patches (50 operations) and reject stale revisions with `409`.
   - Rasterize brush, eraser, lasso, and rectangle operations deterministically in source-pixel coordinates; enforce latest-annotation-wins and active-class-only subtraction.

4. **Frontend**
   - Build the shared shell, navigation, footer, upload controls, dialogs, errors, loading/disabled states, and responsive iLovePDF-inspired visual styling.
   - Implement conversion ordering/reordering, validation display, resource conversion result, and TIFF download.
   - Implement viewer upload, single/grid channel previews, keyboard/channel navigation, zoom/pan/fit, and transfer to annotator without a second upload.
   - Implement annotator canvas with one tested coordinate-transform utility, optimistic strokes, backend overlay refresh, channel switching, class/layer management, visibility-only overlays, mask replacement confirmation, unsaved-change protection, and export dialog.

5. **Documentation and release verification**
   - Document local setup, environment variables, Docker Compose, architecture, supported TIFF scope, v1 limitations, and curl examples for conversion, image upload, annotation creation, mask retrieval, and ZIP export.
   - Run backend, frontend, and Playwright suites; verify local development startup and `docker compose up --build`.

## Data flow

- Browser uploads BMP/TIFF multipart data to `/api/v1`; backend validates and writes UUID-owned files plus metadata under `MULAN_DATA_DIR`.
- TIFF previews are rendered server-side from original raster data into cached PNGs; source TIFF pixel values, bands, CRS, and transforms remain unchanged.
- The viewer and annotator share `image_id`. The annotator sends source-pixel operations to `/api/internal/v1`; backend mutates the canonical mask, records a compact history patch, increments `revision`, and returns lightweight state.
- Overlay PNGs are visualization-only, nearest-neighbor resized, and refreshed from canonical mask state. Export packages are generated from the canonical mask, persisted classes, and optionally the original source TIFF.

## Test plan

- Backend synthetic-raster tests cover conversion ordering/metadata and every specified rejection path; image upload/preview normalization; annotation imports/exports; georeferencing behavior; editing semantics; revision conflicts; undo/redo and redo invalidation; class identity/deletion; and ZIP contents.
- Frontend tests cover navigation, converter ordering, viewer modes/channel selection, viewer-to-annotator transfer, coordinate conversion, class/layer behavior, destructive confirmations, overwrite confirmation, and save/export dialog.
- Playwright covers the three required end-to-end workflows: BMP conversion/download, TIFF viewer-to-annotator transfer, and multi-channel annotation/save/export.
- Each milestone runs its relevant suite; final verification runs all suites and Docker Compose.

## Assumptions

- The empty repository is a greenfield implementation; only `SPEC.md` and `AGENTS.md` currently exist.
- Local Python and Docker were not available in this session, so the plan targets the specified Python 3.12 and Docker toolchain and records their required verification for implementation.
- No database, queue, cloud storage, authentication, or out-of-scope annotation features will be added.
