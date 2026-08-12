from __future__ import annotations

import io
import os
import time

import numpy as np
from PIL import Image

from conftest import tiff


def test_upload_metadata_original_and_preview(client):
    values = np.arange(400, dtype=np.uint16).reshape(20, 20) * 100
    original, name = tiff(np.stack([values, values[::-1]]), descriptions=["Red edge", None])
    raw = original.getvalue()
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(raw), name)}, content_type="multipart/form-data")
    assert response.status_code == 201
    meta = response.get_json()
    assert meta["channel_count"] == 2 and meta["dtype"] == "uint16"
    assert meta["channel_names"] == ["Red edge", None]
    assert client.get(f"/api/v1/images/{meta['image_id']}/file").data == raw
    preview = client.get(f"/api/v1/images/{meta['image_id']}/channels/0/preview?max_size=100")
    assert preview.status_code == 200 and preview.content_type == "image/png"
    image = Image.open(io.BytesIO(preview.data))
    assert image.mode == "L" and image.getextrema()[1] > image.getextrema()[0]


def test_invalid_tiff_and_extension(client):
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(b"not tiff"), "bad.tif")}, content_type="multipart/form-data")
    assert response.status_code == 422
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(b"not tiff"), "bad.png")}, content_type="multipart/form-data")
    assert response.status_code == 415
    png = io.BytesIO(); Image.fromarray(np.zeros((4, 4), np.uint8)).save(png, "PNG"); png.seek(0)
    renamed = client.post("/api/v1/images", data={"file": (png, "renamed.tif")}, content_type="multipart/form-data")
    assert renamed.status_code == 422 and renamed.get_json()["error"]["code"] == "invalid_tiff"


def test_delete_referenced_image_conflicts(client, annotation, uploaded_image):
    assert client.delete(f"/api/v1/images/{uploaded_image['image_id']}").status_code == 409
    assert client.delete(f"/api/v1/annotations/{annotation['annotation_id']}").status_code == 204
    assert client.delete(f"/api/v1/images/{uploaded_image['image_id']}").status_code == 204


def test_cleanup_preserves_images_referenced_by_live_annotations(app, client, annotation, uploaded_image):
    store = app.extensions["mulan_store"]
    old = time.time() - 48 * 3600
    os.utime(store.resource_dir("images", uploaded_image["image_id"]), (old, old))
    result = client.post("/api/internal/v1/cleanup")
    assert result.status_code == 200
    assert client.get(f"/api/v1/images/{uploaded_image['image_id']}").status_code == 200
    os.utime(store.resource_dir("annotations", annotation["annotation_id"]), (old, old))
    result = client.post("/api/internal/v1/cleanup")
    assert result.status_code == 200 and result.get_json()["removed"] == 2
    assert client.get(f"/api/v1/images/{uploaded_image['image_id']}").status_code == 404
