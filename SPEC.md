# MulAn — Multispectral Viewer and Annotator

Build a complete working web application called **MulAn** for converting, viewing, and semantically annotating multispectral imagery.

Implement the application, tests, local-development setup, and Docker deployment described below.

Treat this specification as authoritative. When an implementation detail is not explicitly specified, choose the simplest robust solution consistent with the architecture below. Do not introduce unnecessary infrastructure or features.

Before implementation:

1. Inspect the repository.
2. Create or update an implementation plan.
3. Implement the application incrementally.
4. Run relevant tests after each major subsystem.
5. At completion, run the complete backend, frontend, and end-to-end test suites.
6. Verify both local development and Docker Compose startup.
7. Update the README with exact setup and usage instructions.

Do not stop at scaffolding. Deliver a working application.

---

# 1. Product overview

MulAn is a web-based tool with three core capabilities:

1. Convert ordered single-band BMP images into a multiband TIFF.
2. View multispectral TIFF images channel-by-channel or as a grid.
3. Create ML-ready multi-class semantic-segmentation masks for multispectral TIFF images.

The current version is single-user and session/resource based.

Authentication, accounts, collaborative annotation, persistent user libraries, cloud storage, and dataset management are explicitly out of scope.

---

# 2. Technology stack

## Backend

Use:

* Python 3.12.
* Flask.
* NumPy.
* Rasterio for raster TIFF reading/writing and band metadata.
* Pillow where convenient for BMP validation, PNG previews, and raster drawing.
* Gunicorn for production serving.
* pytest for backend testing.

Keep image processing in reusable service modules rather than Flask route handlers.

Do not implement processing logic directly in the frontend when it belongs to the raster backend.

## Frontend

Use:

* React.
* TypeScript.
* Vite.
* React Router.
* `react-konva` or Konva for the annotation canvas and pointer interaction.
* `@dnd-kit` for sortable file/layer interfaces where required.
* `lucide-react` for icons.
* Native `fetch` unless another HTTP library is genuinely needed.
* Vitest and React Testing Library for frontend tests.
* Playwright for a small number of critical end-to-end workflows.

Do not introduce a large component framework unless necessary.

Use reusable components for upload areas, top navigation, bottom navigation, image controls, dialogs, errors, and buttons.

---

# 3. Production and development architecture

Use one Git repository containing backend and frontend code.

Recommended structure:

```text
mulan/
├── backend/
│   └── mulan/
│       ├── api/
│       ├── services/
│       ├── storage/
│       └── ...
├── frontend/
│   └── src/
├── tests/
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── README.md
└── AGENTS.md
```

The exact structure may vary if there is a clear reason.

## Production

Use a multi-stage Docker build:

1. Build the React/Vite frontend.
2. Copy the compiled frontend into the Python application image.
3. Flask/Gunicorn serves the backend API and compiled SPA/static files.

`docker compose up --build` must start everything necessary.

Do not require:

* PostgreSQL.
* Redis.
* Celery.
* Nginx.
* External object storage.

The initial Compose deployment should require only one application service plus a persistent/local data volume.

## Local development

Support separate frontend/backend development:

```text
Flask backend -> localhost:5000
Vite frontend -> localhost:5173
```

Configure Vite to proxy API calls to Flask.

Document exact commands in the README.

---

# 4. Server-side resource storage

Do not store images or masks inside Flask cookies or browser session objects.

Store large resources on the server filesystem under a configurable directory:

```text
MULAN_DATA_DIR
```

Use UUID identifiers for resources.

Example:

```text
data/
├── images/
│   └── {image_id}/
├── annotations/
│   └── {annotation_id}/
└── conversions/
```

Small metadata may be stored as JSON files.

Abstract filesystem access behind storage/service classes so a database or object store can be introduced later without rewriting the application logic.

Resources are temporary in v1.

Add a configurable TTL, for example:

```text
MULAN_RESOURCE_TTL_HOURS=24
```

Provide cleanup logic for expired resources.

The browser may retain active `image_id` and `annotation_id` values in `sessionStorage`, but public API behavior must never depend on browser cookies.

---

# 5. TIFF data model

MulAn uses standard raster bands.

A multispectral TIFF contains:

```text
width  = W
height = H
bands  = C
```

Rasterio/Python representations should normally be:

```python
image.shape == (C, H, W)
```

The UI may describe this as:

```text
W × H
C channels
```

Do not interchange channel and spatial dimensions internally.

The TIFF produced by MulAn must contain one raster band for each input multispectral channel.

Channel numbering:

```text
API/internal index: 0 ... C-1 where appropriate
Rasterio TIFF band: 1 ... C
UI: Channel 1 ... Channel C
```

Translate explicitly at boundaries.

---

# 6. TIFF metadata

When channel names are known, store them as TIFF band descriptions using Rasterio.

Example:

```text
Band 1 description: 450nm
Band 2 description: 550nm
Band 3 description: 850nm
```

MulAn may additionally store namespaced MulAn metadata in TIFF metadata tags, but must not require those tags to read an otherwise valid TIFF.

Do not invent:

* CRS.
* Geotransform.
* Acquisition parameters.

If an externally uploaded TIFF contains geospatial metadata, preserve it where appropriate.

---

# 7. API organization

Stable/public endpoints use:

```text
/api/v1/
```

Frontend-specific implementation endpoints use:

```text
/api/internal/v1/
```

The web frontend should consume the same public APIs wherever practical.

Internal endpoints are appropriate for UI-specific concepts such as annotation strokes, undo/redo, and overlay rendering.

All JSON errors should follow one shape:

```json
{
  "error": {
    "code": "dimension_mismatch",
    "message": "All BMP images must have identical dimensions.",
    "details": {
      "file": "band_3.bmp",
      "expected": [2048, 1536],
      "received": [1920, 1080]
    }
  }
}
```

Use appropriate status codes:

```text
400 malformed request
404 resource not found
409 state conflict
413 upload too large
415 unsupported media type
422 structurally valid but incompatible image/mask
500 unexpected server error
```

Never expose Python tracebacks in the frontend.

---

# 8. Shared image-resource API

The viewer and annotator operate on the same image resources.

There is no separate viewer-specific backend domain.

## Upload TIFF

```http
POST /api/v1/images
Content-Type: multipart/form-data
```

Input:

```text
file=<TIFF>
```

Accept only `.tif` and `.tiff`.

Validate both:

1. extension;
2. actual TIFF decoding.

Return:

```json
{
  "image_id": "uuid",
  "filename": "sample.tif",
  "width": 2048,
  "height": 1536,
  "channel_count": 8,
  "dtype": "uint16",
  "channel_names": [
    "450nm",
    "550nm",
    null
  ],
  "georeferenced": false
}
```

## Image metadata

```http
GET /api/v1/images/{image_id}
```

Return image metadata.

## Original TIFF

```http
GET /api/v1/images/{image_id}/file
```

Return the original TIFF unchanged.

## Channel preview

```http
GET /api/v1/images/{image_id}/channels/{channel_index}/preview
```

Query options may include:

```text
max_size=1600
normalization=percentile
```

Return:

```http
Content-Type: image/png
```

Do not permanently convert source TIFF channels into PNGs.

Preview images may be cached.

Default high-bit-depth visualization should use percentile normalization, approximately 2nd–98th percentile, with safe handling of constant-valued images.

Normalization changes visualization only.

Never modify source pixel data.

Grid mode should request smaller thumbnails.

## Delete image resource

```http
DELETE /api/v1/images/{image_id}
```

Do not delete an image still referenced by an active annotation resource unless the application handles that relationship safely.

---

# 9. Global UI design

The visual language should be inspired by iLovePDF:

* clean white/light surfaces;
* prominent red primary action color;
* bold simple headings;
* large centered upload actions;
* rounded cards/buttons;
* restrained shadows;
* uncluttered layouts;
* simple line icons;
* clear visual hierarchy.

Do not copy proprietary logos or assets.

Use MulAn branding and placeholder/original icons.

## Top toolbar

Every page contains a fixed or stable top toolbar.

Left to right:

```text
MulAn logo
Convert
Viewer
Annotator
...
User placeholder icon aligned right
```

Clicking the MulAn logo returns home.

Feature buttons navigate to their pages.

The user icon is a non-functional placeholder for future account functionality.

## Bottom toolbar

Every page contains a small bottom footer/toolbar with placeholder links:

```text
Documentation
GitHub
```

---

# 10. Home page

Route:

```text
/
```

Create three large feature cards:

```text
BMP → TIFF
Multispectral Viewer
Multispectral Annotator
```

Each card contains:

* icon;
* title;
* short description;
* clickable navigation.

Do not reproduce unrelated iLovePDF homepage sections.

---

# 11. Feature 1 — BMP → TIFF converter

Route:

```text
/convert
```

The converter combines ordered single-band BMP files into one multiband TIFF.

Each BMP represents exactly one multispectral band.

Input order determines TIFF band order.

## BMP interpretation

The backend must not silently convert color imagery into grayscale.

For v1, input bands must decode to a single grayscale raster.

A BMP encoded as RGB may only be collapsed to one band if all RGB components are identical for every pixel; otherwise reject it as a multi-channel/color BMP.

All input bands must have:

* identical width;
* identical height;
* compatible/sample datatype.

Do not silently rescale one input to match another.

---

# 12. Converter public API

```http
POST /api/v1/convert/bmp-to-tiff
Content-Type: multipart/form-data
```

Use repeated `files` fields:

```text
files=band_1.bmp
files=band_2.bmp
files=band_3.bmp
```

The order returned by the server's multipart file-list handling is authoritative.

Optional fields:

```text
channel_names=["450nm","550nm","850nm"]
output_name=sample.tif
response_mode=direct
```

`channel_names`, when provided, must contain exactly one entry per input band.

An optional manifest may also be accepted for advanced clients:

```json
{
  "bands": [
    {"file_index": 0, "name": "450nm"},
    {"file_index": 1, "name": "550nm"}
  ]
}
```

If a manifest is present, validate it strictly.

## Direct response mode

Default:

```text
response_mode=direct
```

Return the TIFF directly:

```http
200 OK
Content-Type: image/tiff
Content-Disposition: attachment; filename="multispectral.tif"
X-Channel-Count: 3
```

This mode must work without the web UI and be usable from:

* curl;
* Python;
* MATLAB;
* arbitrary HTTP clients.

## Resource response mode

The browser converter UI should use:

```text
response_mode=resource
```

The backend performs the identical conversion, stores the resulting TIFF as an image resource, and returns:

```json
{
  "image_id": "uuid",
  "filename": "multispectral.tif",
  "width": 2048,
  "height": 1536,
  "channel_count": 3,
  "channel_names": [
    "450nm",
    "550nm",
    "850nm"
  ],
  "download_url": "/api/v1/images/{image_id}/file"
}
```

Return `201 Created`.

This reconciles standalone API use with the UI's separate download page.

Do not maintain two conversion implementations.

Both modes must call the same conversion service.

---

# 13. Converter validation

Reject:

* no files;
* non-BMP files;
* corrupt BMPs;
* unsupported color BMPs;
* mismatched width;
* mismatched height;
* incompatible datatype;
* channel-name count mismatch.

The generated TIFF must preserve exact input-band order.

Do not invent geospatial information because BMP sources do not contain it.

---

# 14. Converter frontend

When empty:

* large drag/drop area;
* prominent file-selection button;
* clear text explaining that each BMP becomes one TIFF channel.

After upload:

Display ordered cards/rows.

Each row should visibly show:

```text
Channel 1
band_450.bmp

Channel 2
band_550.bmp
```

Allow:

* drag-and-drop reordering;
* explicit move up/down if helpful;
* deletion;
* adding more bands.

Perform client-side preliminary extension/dimension checks where convenient, but the backend remains authoritative.

Show validation failures next to the affected file.

Primary action:

```text
Convert to TIF
```

After successful resource-mode conversion, navigate to:

```text
/convert/result/{image_id}
```

Display:

* filename;
* dimensions;
* channel count;
* channel names if provided;
* prominent `Download TIF` button.

The button downloads:

```text
/api/v1/images/{image_id}/file
```

---

# 15. Feature 2 — multispectral viewer

Route:

```text
/viewer
```

The viewer is a frontend over the shared image-resource API.

It does not have a separate `/viewer` API namespace.

## Empty state

Allow:

* file-selection upload;
* TIFF drag/drop.

Only `.tif` and `.tiff` are accepted.

After upload, create an image resource through:

```text
POST /api/v1/images
```

---

# 16. Viewer single-channel mode

This is the default.

Display one channel prominently.

Controls:

```text
Previous
Channel 3 / 8
Next
```

Disable previous on the first channel.

Disable next on the final channel.

Changing channels must not reload the page.

Support left/right keyboard navigation when focus behavior makes this safe.

Provide basic image navigation:

* zoom in;
* zoom out;
* fit to viewport;
* pan when zoomed.

Preserve aspect ratio.

Display compact metadata:

```text
sample.tif
2048 × 1536
8 channels
Channel: 550nm
```

If no channel name exists, show only channel number.

---

# 17. Viewer grid mode

Toggle:

```text
Single Channel | Grid
```

Grid mode displays all channels in a responsive grid.

Each tile contains:

* thumbnail;
* `Channel N`;
* band description/name when available.

Use reduced-size preview requests rather than full-resolution previews.

Do not eagerly transfer full-resolution data for every channel.

Clicking a grid tile should:

1. select that channel;
2. switch to single-channel mode.

---

# 18. Open in Annotator

Provide:

```text
Open in Annotator
```

Navigate using the existing resource:

```text
/annotator?image_id={image_id}
```

Do not upload the TIFF again.

The annotator must operate on the original TIFF resource, not a normalized PNG preview.

---

# 19. Feature 3 — multispectral semantic annotator

Route:

```text
/annotator
```

The annotator creates multi-class **semantic segmentation** masks.

It does not implement instance segmentation.

Annotations apply spatially across the entire multispectral image, independent of the currently displayed spectral channel.

Switching channel changes the background visualization only.

---

# 20. Canonical annotation representation

The canonical mask is:

```text
one raster band
width = source width
height = source height
integer class IDs
```

Conceptually:

```text
source TIFF: C × H × W
mask TIFF:   H × W
```

Values:

```text
0 = Background
1 = class 1
2 = class 2
...
```

Class `0` exists by default.

For v1, unannotated pixels are considered Background and therefore have value `0`.

Do not treat `0` as TIFF nodata.

Metadata should include:

```json
"background_id": 0,
"ignore_id": null
```

This allows a future distinct ignore/unlabeled class without changing the current format.

Internally, the annotation backend may use `uint16` consistently.

On export:

* use `uint8` if maximum class ID <= 255;
* otherwise use `uint16`.

Never encode semantic labels as RGB mask colors.

---

# 21. Geospatial behavior of annotation masks

If the source TIFF contains valid:

* CRS;
* affine transform;
* spatial extent information supported by Rasterio;

copy the relevant georeferencing to the exported mask.

The mask must spatially align with the source.

If the source is not georeferenced, do not invent georeferencing.

The source image itself must always remain unchanged.

---

# 22. Annotation class model

Each class contains:

```json
{
  "id": 1,
  "name": "Vegetation",
  "description": "Healthy vegetation",
  "color": "#44AA44",
  "order": 1,
  "visible": true
}
```

Only these are semantically persisted:

* id;
* name;
* description;
* display color;
* ordering metadata where desired.

Visibility is fundamentally UI state and must never change mask values.

Class IDs are persistent.

Class ordering must never determine class IDs.

Deleting class `2` does not cause class `3` to become class `2`.

Never automatically renumber existing classes.

---

# 23. Annotation metadata format

Export `annotations.json`.

Example:

```json
{
  "format": "mulan-semantic-segmentation",
  "version": "1.0",
  "image": {
    "filename": "multispectral.tif",
    "width": 2048,
    "height": 1536,
    "channels": 8,
    "channel_names": [
      "450nm",
      "550nm",
      "850nm"
    ]
  },
  "mask": {
    "filename": "mask.tif",
    "dtype": "uint8",
    "background_id": 0,
    "ignore_id": null
  },
  "classes": [
    {
      "id": 0,
      "name": "Background",
      "description": "",
      "color": "#000000"
    },
    {
      "id": 1,
      "name": "Vegetation",
      "description": "Healthy vegetation",
      "color": "#44AA44"
    }
  ]
}
```

Optional geospatial metadata may be recorded if available, but the TIFF itself remains authoritative for georeferencing.

---

# 24. Annotation public API

## Create annotation

```http
POST /api/v1/annotations
Content-Type: multipart/form-data
```

Accept exactly one source-image option:

```text
image=<TIFF>
```

or:

```text
image_id=<existing image resource UUID>
```

Optional:

```text
mask=<mask.tif>
metadata=<annotations.json>
```

If an image is uploaded directly, create an image resource internally and return its `image_id`.

Return:

```json
{
  "annotation_id": "uuid",
  "image_id": "uuid",
  "filename": "sample.tif",
  "width": 2048,
  "height": 1536,
  "channel_count": 8,
  "revision": 0,
  "saved_revision": 0,
  "classes": [
    {
      "id": 0,
      "name": "Background",
      "description": "",
      "color": "#000000"
    }
  ]
}
```

## Retrieve annotation

```http
GET /api/v1/annotations/{annotation_id}
```

Return:

* source image information;
* classes;
* current revision;
* saved revision;
* mask dtype;
* simple class statistics where inexpensive, such as pixel count.

The selected area for any class is canonically:

```python
mask == class_id
```

An external ML client must not need separate files for every class.

## Retrieve canonical mask

```http
GET /api/v1/annotations/{annotation_id}/mask
```

Return:

```http
Content-Type: image/tiff
Content-Disposition: attachment; filename="mask.tif"
```

The TIFF must contain one integer band.

## Replace/import mask

```http
PUT /api/v1/annotations/{annotation_id}/mask
Content-Type: multipart/form-data
```

Fields:

```text
mask=<mask.tif>
metadata=<optional annotations.json>
overwrite=false
```

Validate:

* TIFF container;
* exactly one raster band;
* integer datatype;
* exact source width;
* exact source height;
* non-negative class IDs.

If the current annotation contains meaningful edits and `overwrite` is false:

```http
409 Conflict
```

Return an error stating that explicit overwrite is required.

The UI then presents a warning and retries with:

```text
overwrite=true
```

If metadata is absent, inspect unique class IDs and create placeholder classes without renumbering:

```text
0 -> Background
1 -> Class 1
2 -> Class 2
5 -> Class 5
```

Optionally accept a ZIP containing:

```text
mask.tif
annotations.json
```

as an import convenience.

## Class endpoints

Create:

```http
POST /api/v1/annotations/{annotation_id}/classes
```

Edit:

```http
PATCH /api/v1/annotations/{annotation_id}/classes/{class_id}
```

Delete:

```http
DELETE /api/v1/annotations/{annotation_id}/classes/{class_id}
```

Deleting a class:

* is forbidden for class `0`;
* assigns every pixel currently containing that ID to `0`;
* does not renumber other classes.

Reordering may be represented in metadata but never alters the mask.

## Export

```http
GET /api/v1/annotations/{annotation_id}/export?include_image=false
```

Return:

```text
annotation-mask.zip
├── mask.tif
└── annotations.json
```

With:

```text
include_image=true
```

return:

```text
annotation.zip
├── image.tif
├── mask.tif
└── annotations.json
```

The exported `image.tif` must be byte-for-byte the original uploaded/stored source whenever practical.

## Delete annotation

```http
DELETE /api/v1/annotations/{annotation_id}
```

Delete annotation-owned temporary resources safely.

---

# 25. Annotation semantics

Only one semantic class can own a pixel.

The canonical mask itself enforces this.

Use:

```text
latest annotation wins
```

Example:

```text
pixel currently = class 2
user paints class 5
pixel becomes = class 5
```

Layer order does not affect this.

---

# 26. Annotation editing architecture

The backend canonical mask is authoritative.

Do not reconstruct the canonical mask from visible frontend layers when the user saves.

Frontend pointer interaction should feel immediate, but completed annotation operations should be sent to backend internal endpoints.

Recommended internal operation endpoint:

```http
POST /api/internal/v1/annotations/{annotation_id}/operations
```

Example brush operation:

```json
{
  "base_revision": 14,
  "tool": "brush_add",
  "class_id": 3,
  "radius": 12,
  "points": [
    {"x": 102, "y": 220},
    {"x": 106, "y": 224}
  ]
}
```

All coordinates are source-image pixel coordinates, not CSS/display coordinates.

Supported operations:

```text
brush_add
erase
lasso_add
lasso_subtract
rectangle_add
rectangle_subtract
```

Return the new annotation revision.

Use revision numbers to reject obviously stale/conflicting operations where appropriate.

---

# 27. Raster operation semantics

## Brush

Paint class ID onto pixels along the stroke.

Painting over another class replaces it.

## Eraser

Erase only pixels belonging to the active class.

Matching pixels become `0`.

Pixels belonging to another class remain unchanged.

## Lasso Add

Rasterize the closed polygon.

Every contained pixel becomes the active class.

## Lasso Subtract

Within the polygon, only pixels belonging to the active class become `0`.

Other classes are unchanged.

## Rectangle Add

All pixels in the rectangle become active class.

## Rectangle Subtract

Within the rectangle, pixels matching the active class become `0`.

Other classes remain unchanged.

Use deterministic rasterization.

---

# 28. Undo and redo

Internal endpoints may use:

```http
POST /api/internal/v1/annotations/{annotation_id}/undo
POST /api/internal/v1/annotations/{annotation_id}/redo
```

Undo/redo applies at minimum to:

* brush;
* eraser;
* lasso add/subtract;
* rectangle add/subtract.

Channel changes do not affect history.

Use a bounded history, for example 50 editing operations.

Avoid storing a complete full-resolution mask copy for every operation when possible.

Prefer storing compact changed-region information or equivalent reversible patches.

A new operation after undo invalidates redo history.

---

# 29. Annotation overlay API

Provide an internal rendering endpoint, for example:

```http
GET /api/internal/v1/annotations/{annotation_id}/overlay
```

Allow a requested preview size.

Return a transparent PNG where class IDs are mapped to their visualization colors.

This PNG is for visualization only.

It is never the canonical segmentation mask.

Use nearest-neighbor resampling for label-mask resizing.

Frontend may draw an optimistic temporary representation during an active pointer stroke and refresh the canonical overlay after the operation completes.

---

# 30. Annotator layout

The annotator consists of:

```text
global top toolbar

left tool bar | central image canvas | right class/layer panel

global bottom toolbar
```

The central canvas should receive most of the available width/height.

Only single-channel viewing is used inside the annotator.

---

# 31. Annotator image navigation

Reuse viewer channel-preview behavior.

Controls:

```text
Previous Channel
Channel N / C
Next Channel
```

Also provide:

* zoom in;
* zoom out;
* fit;
* pan.

Changing channel must preserve:

* annotations;
* active class;
* active tool;
* zoom level where practical;
* viewport center where practical;
* undo/redo history.

The overlay must remain pixel-aligned with every channel.

---

# 32. Coordinate transforms

The displayed image can be scaled, translated, and zoomed.

All edit operations must eventually be expressed in original image pixel coordinates.

Implement a single reusable coordinate-transform utility.

Test it.

Do not use CSS/display coordinates directly as annotation coordinates.

Exported masks must always have source-image resolution regardless of viewer zoom.

---

# 33. Left annotation toolbar

Required tools:

```text
Brush
Eraser
Lasso Add
Lasso Subtract
Rectangle Add
Rectangle Subtract
Undo
Redo
```

Use compact icon buttons with tooltips.

Visually identify the active tool.

Brush/eraser should expose brush-radius or brush-size control.

Undo/Redo buttons must disable when unavailable.

---

# 34. Right class/layer panel

Each class row displays:

* color swatch;
* class ID;
* name;
* visibility control;
* edit control;
* delete control;
* drag handle.

The active class must be visually obvious.

Provide:

```text
Add class
```

Editing a class supports:

```text
name
description
display color
```

Do not allow ordinary editing of `class_id`.

Layer drag/drop affects ordering only.

It must never modify mask pixel values or class IDs.

Visibility affects overlays only.

It must never modify exported data.

---

# 35. Class deletion UX

Deleting a non-background class must show confirmation:

```text
Delete "Vegetation"?

All pixels assigned to this class will become Background.

Cancel | Delete
```

Only perform the public class DELETE request after confirmation.

Class `0` cannot be deleted.

---

# 36. Apply Mask UI

Place:

```text
Apply Mask
```

above the layer panel.

Support:

* selecting `mask.tif`;
* optionally selecting accompanying `annotations.json`;
* dropping a compatible mask;
* optionally dropping/importing the ZIP mask package.

When existing annotations are present, show:

```text
Replace current annotations?

The imported mask will replace the current semantic segmentation.
Existing edits may be lost.

Cancel | Replace
```

Do not merge masks in v1.

Import is replacement.

---

# 37. Save Changes behavior

Place:

```text
Save changes
```

below the layer panel.

Every completed editing operation has already updated server-side annotation state.

Therefore Save must not rebuild the mask.

`Save changes` should:

1. validate the annotation state;
2. mark the current revision as `saved_revision`;
3. persist class metadata;
4. open the export dialog.

Provide an internal endpoint if needed:

```http
POST /api/internal/v1/annotations/{annotation_id}/save
```

Unsaved state is:

```text
revision != saved_revision
```

---

# 38. Export dialog

After saving, open a modal with:

```text
Download Mask
Download Image + Mask
```

`Download Mask`:

```text
mask.tif
annotations.json
```

inside a ZIP.

`Download Image + Mask` additionally includes the source image.

---

# 39. Browser-close/navigation protection

When:

```text
revision != saved_revision
```

warn the user before deliberately leaving the annotator through MulAn navigation.

Use browser `beforeunload` behavior where supported, without producing excessive prompts.

---

# 40. Mask validation

Reject imported masks if:

* extension is unsupported;
* file is not actually TIFF;
* TIFF is unreadable;
* raster has more than one band;
* dimensions differ;
* datatype is not integer;
* negative IDs exist;
* class metadata contains invalid IDs;
* metadata conflicts with mask class IDs.

When additional IDs occur in the mask but metadata omits them, placeholder classes may be created.

Do not silently change class IDs.

---

# 41. Viewer/annotator performance

Multispectral imagery may be large.

Avoid:

* repeatedly sending full TIFFs;
* decoding all full-resolution bands for grid mode;
* recreating every preview after annotation edits;
* transferring the full canonical mask after every brush stroke.

Use:

* cached PNG previews;
* thumbnail previews for grid mode;
* server-side annotation operations;
* lightweight revision responses;
* overlay previews;
* source-coordinate operations.

Any caching must be invalidated correctly.

---

# 42. Upload security and robustness

Implement:

* sanitized filenames;
* UUID-generated storage paths;
* protection against path traversal;
* configurable upload-size limit;
* safe handling of malformed images;
* no shell commands constructed from filenames;
* resource cleanup.

Do not trust file extensions alone.

Do not trust browser MIME types alone.

---

# 43. API documentation

Provide concise API documentation in the repository.

Include curl examples for at least:

## Conversion

```bash
curl -X POST \
  -F "files=@450.bmp" \
  -F "files=@550.bmp" \
  -F "files=@850.bmp" \
  -F 'channel_names=["450nm","550nm","850nm"]' \
  -F "response_mode=direct" \
  http://localhost:5000/api/v1/convert/bmp-to-tiff \
  --output multispectral.tif
```

## TIFF upload

Demonstrate creating an `image_id`.

## Annotation creation

Demonstrate creating annotation from either uploaded TIFF or `image_id`.

## Mask retrieval

Demonstrate downloading `mask.tif`.

## Export

Demonstrate downloading a ZIP annotation package.

---

# 44. Backend tests

Create synthetic images programmatically.

Do not require committed large binary fixtures.

Test at minimum:

* BMP order becomes TIFF band order.
* channel descriptions persist.
* dimension mismatch rejected.
* non-BMP rejected.
* true RGB BMP rejected.
* valid TIFF upload.
* invalid TIFF rejected.
* channel count detection.
* preview endpoint.
* high-bit-depth preview normalization.
* valid annotation creation.
* mask dimension validation.
* multi-band mask rejection.
* float mask rejection.
* latest-annotation-wins behavior.
* eraser only removes active class.
* lasso add/subtract.
* rectangle add/subtract.
* undo.
* redo.
* redo invalidation after new operation.
* persistent class IDs.
* deleting class converts matching pixels to `0`.
* mask export values.
* annotation JSON.
* full ZIP export.
* source GeoTIFF georeferencing copied to mask.
* non-georeferenced source does not receive invented georeferencing.

---

# 45. Frontend tests

Test key state transitions and controls.

At minimum:

* global navigation;
* converter ordering;
* viewer mode toggle;
* viewer channel navigation;
* grid tile selection;
* viewer → annotator transfer;
* class creation/editing;
* layer ordering does not alter IDs;
* visibility toggle;
* destructive delete confirmation;
* mask overwrite confirmation;
* Save dialog.

---

# 46. End-to-end tests

Use Playwright for a small critical set rather than attempting exhaustive browser coverage.

Required E2E workflows:

## Workflow A

```text
BMP upload
→ reorder
→ convert
→ result page
→ download TIFF
```

## Workflow B

```text
TIFF upload
→ viewer
→ change channel
→ grid mode
→ select channel
→ Open in Annotator
```

## Workflow C

```text
TIFF upload
→ create class
→ rectangle/brush annotation
→ change spectral channel
→ annotation remains aligned
→ save
→ export mask package
```

---

# 47. UI quality

The completed application should look intentionally designed rather than like raw developer scaffolding.

Requirements:

* responsive desktop-first layout;
* sensible tablet behavior;
* consistent spacing;
* clear hierarchy;
* disabled/loading/error states;
* accessible labels;
* keyboard-focus states;
* useful tooltips;
* no overflowing panels at normal laptop resolutions;
* no unstyled native file-input elements exposed unnecessarily.

The annotator may prioritize desktop use.

---

# 48. Out of scope

Do not implement in v1:

* authentication;
* user accounts;
* permissions;
* PostgreSQL;
* Redis;
* cloud object storage;
* collaborative editing;
* concurrent annotators;
* video;
* image sequences;
* object tracking;
* instance segmentation;
* independent bounding-box object datasets;
* keypoints;
* skeletons;
* polygon vertex editing after creation;
* per-object attributes;
* annotation review;
* dataset management;
* model inference;
* AI-assisted segmentation;
* GeoTIFF reprojection;
* CRS editing;
* arbitrary OME-TIFF/hyperstack semantics;
* mask merging.

---

# 49. Supported TIFF scope

MulAn v1 supports TIFFs that Rasterio can interpret as a raster dataset with:

```text
width > 0
height > 0
count >= 1
```

Each Rasterio band is treated as one multispectral channel.

Do not attempt to interpret arbitrary TIFF page structures, microscopy hyperstacks, OME multidimensional axes, or exotic TIFF layouts beyond what Rasterio exposes as ordinary bands.

Fail cleanly with an explanatory error for unsupported layouts.

---

# 50. Completion criteria

The project is complete only when all of the following are true:

```text
docker compose up --build
```

starts a functional application.

Local backend/frontend development instructions work.

The home page exposes all three features.

BMP conversion works from both UI and standalone API.

Generated TIFF band order exactly matches BMP ordering.

Viewer supports single and grid views.

Viewer can open the same image resource in the annotator without re-upload.

Annotator supports all required edit tools.

Annotations remain constant while switching spectral channels.

The canonical mask contains one integer class ID per pixel.

Class IDs survive reorder/delete operations correctly.

Mask imports are validated.

Existing annotation overwrite requires explicit confirmation.

Undo/redo works.

Mask export works.

Image + mask export works.

GeoTIFF alignment metadata is preserved when available.

Backend tests pass.

Frontend tests pass.

Critical Playwright workflows pass.

README documents local use, Docker use, architecture, API usage, and known v1 limitations.

Do not mark the task complete while tests are failing unless a failure is caused by a demonstrably unavailable external system. There should be no required external system for this application.
