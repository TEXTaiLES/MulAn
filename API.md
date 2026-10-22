# MulAn HTTP API v1

Public endpoints live under `/api/v1`. UI editing endpoints live under `/api/internal/v1`. MulAn's backend serves both on top of HESTIA: images and saved annotations are read from and written to HESTIA's MulAn endpoints, and HESTIA authorizes every call.

## Authentication

Every `/api/v1` and `/api/internal/v1` endpoint requires a HESTIA session. MulAn reads the HESTIA portal's `textailes_refresh_token` cookie (name set by `HESTIA_COOKIE_NAME`) and forwards it to HESTIA. Without a valid session, endpoints return `401 unauthenticated`; without the needed HESTIA capability, `403 forbidden`.

- `GET /api/v1/session` reports the caller's HESTIA user and capabilities (`images_read`, `images_create`, `annotations_read`, `annotations_create`, `annotations_update`), plus `login_url` and `logout_url`.
- `GET /auth/login` redirects to the HESTIA portal's login page, which returns the user to MulAn's front page.
- `GET /auth/logout` redirects to the HESTIA portal's logout.

The examples use `MULAN_URL` for the server address and `HESTIA_TOKEN` for the cookie value copied from a signed-in browser:

```bash
export MULAN_URL=http://localhost:5001
export HESTIA_TOKEN=...
alias mulan='curl -b "textailes_refresh_token=$HESTIA_TOKEN"'
```

Errors have one shape, and HESTIA's errors are passed through unchanged:

```json
{"error":{"code":"dimension_mismatch","message":"All BMP images must have identical dimensions.","details":{}}}
```

`502 hestia_unavailable` means MulAn could not reach HESTIA.

## Convert ordered BMP channels

The repeated `files` order defines TIFF band-group order. A grayscale BMP contributes one band. An RGB BMP contributes three adjacent bands in deterministic `R`, `G`, `B` order, with default descriptions such as `scene:R`, `scene:G`, and `scene:B`. Mixed grayscale and RGB files are supported; all inputs must have matching spatial dimensions and compatible integer datatypes. Pixel values are copied without RGB-to-grayscale conversion. Direct mode returns the TIFF itself.

```bash
mulan -X POST \
  -F "files=@450.bmp" \
  -F "files=@550.bmp" \
  -F "files=@850.bmp" \
  -F 'channel_names=["450nm","550nm","850nm"]' \
  -F "response_mode=direct" \
  $MULAN_URL/api/v1/convert/bmp-to-tiff \
  --output multispectral.tif
```

`channel_names` contains one string or `null` per final expanded TIFF band, not per uploaded file. For example, grayscale + RGB + grayscale requires five entries.

Use `response_mode=resource` to store the TIFF in HESTIA as a new image (needs `images_create`) and receive JSON containing its HESTIA `image_id`, the expanded `channel_count`, and `download_url`. Optional `output_name` controls the safe download name. An advanced `manifest` may contain exactly one `{file_index,name}` entry per file; a name assigned to an RGB file expands with `:R`, `:G`, and `:B` suffixes.

## Images

Images are HESTIA multispectral images, identified by HESTIA's UUID `image_id`.

```bash
# List (page, per_page up to 100, q filename filter, sort=created_at|filename, has_annotation=true|false)
mulan "$MULAN_URL/api/v1/images?q=scan&per_page=20"

# Upload a TIFF to HESTIA (needs images_create)
mulan -X POST -F "file=@multispectral.tif" $MULAN_URL/api/v1/images

# Metadata, unchanged original, and zero-based channel preview
mulan $MULAN_URL/api/v1/images/IMAGE_ID
mulan -o original.tif $MULAN_URL/api/v1/images/IMAGE_ID/file
mulan -o channel.png \
  "$MULAN_URL/api/v1/images/IMAGE_ID/channels/0/preview?max_size=800&normalization=percentile"

# The saved annotation package from HESTIA, optionally with the source TIFF
mulan -o annotation-mask.zip $MULAN_URL/api/v1/images/IMAGE_ID/annotation/package
mulan -o annotation.zip "$MULAN_URL/api/v1/images/IMAGE_ID/annotation/package?include_image=true"
```

Previews are rendered from a local copy of the HESTIA image that MulAn caches; each request still checks access with HESTIA. HESTIA has no image delete endpoint.

## Annotation working copies

Opening an image creates a working copy of its HESTIA annotation (or a blank mask when it has none). Editing changes only the working copy; saving writes it to HESTIA. A working copy belongs to the HESTIA user who opened it; other users get `404`.

```bash
# Open (needs images_read and annotations_read)
mulan -X POST -F "image_id=IMAGE_ID" $MULAN_URL/api/v1/annotations

# Retrieve state and the working copy's one-band mask
mulan $MULAN_URL/api/v1/annotations/ANNOTATION_ID
mulan -o mask.tif $MULAN_URL/api/v1/annotations/ANNOTATION_ID/mask

# Replace the mask (explicit overwrite is required when pixels are already labeled)
mulan -X PUT -F "mask=@mask.tif" -F "metadata=@annotations.json" \
  -F "overwrite=true" \
  $MULAN_URL/api/v1/annotations/ANNOTATION_ID/mask
```

Annotation resources include `hestia_revision`: the HESTIA revision the working copy was opened from or last saved as, or `null` when HESTIA has no annotation for the image yet.

Mask replacement is recorded in the same bounded history used by annotation operations. The internal undo and redo endpoints restore both mask pixels and imported class metadata.

Class endpoints are `POST /annotations/{id}/classes`, `PATCH /annotations/{id}/classes/{class_id}`, and `DELETE /annotations/{id}/classes/{class_id}`. Class 0 cannot be deleted or renamed (HESTIA requires it to be `Background`); deleting another class changes only matching mask pixels to 0 and never renumbers other IDs.

## UI editing endpoints

- `POST /api/internal/v1/annotations/{id}/operations`
- `POST /api/internal/v1/annotations/{id}/undo`
- `POST /api/internal/v1/annotations/{id}/redo`
- `POST /api/internal/v1/annotations/{id}/save`
- `GET /api/internal/v1/annotations/{id}/overlay?max_size=1600&visible_ids=1,3`
- `PATCH /api/internal/v1/annotations/{id}/class-order`

Operation bodies contain `base_revision`, `tool`, `class_id`, source-pixel `points`, and `radius` for brushes. Supported tools are `brush_add`, `erase`, `lasso_add`, `lasso_subtract`, `rectangle_add`, and `rectangle_subtract`. A stale `base_revision` returns `409`.

`save` uploads the working copy to HESTIA as a `mask.tif` + `annotations.json` package. It needs `annotations_create` for an image's first annotation and `annotations_update` afterwards. MulAn sends the HESTIA revision the working copy started from, so a save that would overwrite a newer HESTIA annotation returns `409 annotation_exists` or `409 annotation_revision_conflict` and leaves the working copy unsaved. Saving without changes does not create a new HESTIA revision.
