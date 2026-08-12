# MulAn HTTP API v1

Public endpoints live under `/api/v1`. UI editing endpoints live under `/api/internal/v1`. API state is identified only by UUID resource IDs and does not depend on cookies.

Errors have one shape:

```json
{"error":{"code":"dimension_mismatch","message":"All BMP images must have identical dimensions.","details":{}}}
```

## Convert ordered BMP channels

The repeated `files` order defines TIFF band-group order. A grayscale BMP contributes one band. An RGB BMP contributes three adjacent bands in deterministic `R`, `G`, `B` order, with default descriptions such as `scene:R`, `scene:G`, and `scene:B`. Mixed grayscale and RGB files are supported; all inputs must have matching spatial dimensions and compatible integer datatypes. Pixel values are copied without RGB-to-grayscale conversion. Direct mode returns the TIFF itself.

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

`channel_names` contains one string or `null` per final expanded TIFF band, not per uploaded file. For example, grayscale + RGB + grayscale requires five entries.

Use `response_mode=resource` to receive JSON containing `image_id`, the expanded `channel_count`, and `download_url`. Optional `output_name` controls the safe download name. An advanced `manifest` may contain exactly one `{file_index,name}` entry per file; a name assigned to an RGB file expands with `:R`, `:G`, and `:B` suffixes.

## Image resources

```bash
# Upload and receive an image_id
curl -X POST -F "file=@multispectral.tif" \
  http://localhost:5000/api/v1/images

# Metadata, unchanged original, and zero-based channel preview
curl http://localhost:5000/api/v1/images/IMAGE_ID
curl -o original.tif http://localhost:5000/api/v1/images/IMAGE_ID/file
curl -o channel.png \
  "http://localhost:5000/api/v1/images/IMAGE_ID/channels/0/preview?max_size=800&normalization=percentile"

curl -X DELETE http://localhost:5000/api/v1/images/IMAGE_ID
```

An image referenced by an active annotation cannot be deleted.

## Annotations

Create from an existing image resource:

```bash
curl -X POST -F "image_id=IMAGE_ID" \
  http://localhost:5000/api/v1/annotations
```

Or upload the source TIFF directly:

```bash
curl -X POST -F "image=@multispectral.tif" \
  http://localhost:5000/api/v1/annotations
```

Both forms optionally accept `mask=@mask.tif` and `metadata=@annotations.json`. Exactly one of `image` and `image_id` is required.

```bash
# Retrieve state and canonical one-band mask
curl http://localhost:5000/api/v1/annotations/ANNOTATION_ID
curl -o mask.tif \
  http://localhost:5000/api/v1/annotations/ANNOTATION_ID/mask

# Replace a mask (explicit overwrite is required when pixels are already labeled)
curl -X PUT -F "mask=@mask.tif" -F "metadata=@annotations.json" \
  -F "overwrite=true" \
  http://localhost:5000/api/v1/annotations/ANNOTATION_ID/mask

# Mask + JSON package, or package including the byte-preserved source
curl -o annotation-mask.zip \
  "http://localhost:5000/api/v1/annotations/ANNOTATION_ID/export?include_image=false"
curl -o annotation.zip \
  "http://localhost:5000/api/v1/annotations/ANNOTATION_ID/export?include_image=true"
```

Mask replacement is recorded in the same bounded history used by annotation operations. The internal undo and redo endpoints restore both mask pixels and imported class metadata.

Class endpoints are `POST /annotations/{id}/classes`, `PATCH /annotations/{id}/classes/{class_id}`, and `DELETE /annotations/{id}/classes/{class_id}`. Class 0 cannot be deleted; deleting another class changes only matching mask pixels to 0 and never renumbers other IDs.

## UI editing endpoints

- `POST /api/internal/v1/annotations/{id}/operations`
- `POST /api/internal/v1/annotations/{id}/undo`
- `POST /api/internal/v1/annotations/{id}/redo`
- `POST /api/internal/v1/annotations/{id}/save`
- `GET /api/internal/v1/annotations/{id}/overlay?max_size=1600&visible_ids=1,3`
- `PATCH /api/internal/v1/annotations/{id}/class-order`

Operation bodies contain `base_revision`, `tool`, `class_id`, source-pixel `points`, and `radius` for brushes. Supported tools are `brush_add`, `erase`, `lasso_add`, `lasso_subtract`, `rectangle_add`, and `rectangle_subtract`. A stale `base_revision` returns `409`.
