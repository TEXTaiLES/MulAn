from __future__ import annotations

import io
import os
import time

import numpy as np
from PIL import Image

from conftest import tiff
from fake_hestia import TOKEN


def test_upload_stores_image_in_hestia_and_serves_original_and_preview(client, hestia):
    values = np.arange(400, dtype=np.uint16).reshape(20, 20) * 100
    original, name = tiff(np.stack([values, values[::-1]]), descriptions=["Red edge", None])
    raw = original.getvalue()
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(raw), name)}, content_type="multipart/form-data")
    assert response.status_code == 201
    meta = response.get_json()
    assert meta["image_id"] in hestia.images and hestia.files[meta["image_id"]] == raw
    assert meta["channel_count"] == 2 and meta["dtype"] == "uint16"
    assert meta["channel_names"] == ["Red edge", None]
    assert meta["created_by"]["id"] == "user-1"
    assert client.get(f"/api/v1/images/{meta['image_id']}").get_json() == meta
    original_file = client.get(f"/api/v1/images/{meta['image_id']}/file")
    assert original_file.data == raw and original_file.headers["Content-Type"] == "image/tiff"
    preview = client.get(f"/api/v1/images/{meta['image_id']}/channels/0/preview?max_size=100")
    assert preview.status_code == 200 and preview.content_type == "image/png"
    assert "private" in preview.headers["Cache-Control"]
    image = Image.open(io.BytesIO(preview.data))
    assert image.mode == "L" and image.getextrema()[1] > image.getextrema()[0]


def test_list_forwards_supported_filters_to_hestia(client, hestia, uploaded_image):
    response = client.get("/api/v1/images?page=2&per_page=10&q=scan&has_annotation=false&ignored=1")
    assert response.status_code == 200
    assert [item["image_id"] for item in response.get_json()["items"]] == [uploaded_image["image_id"]]
    assert "list_images [('has_annotation', 'false'), ('page', '2'), ('per_page', '10'), ('q', 'scan')]" in hestia.calls


def test_hestia_validation_errors_reach_the_client(client):
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(b"not tiff"), "bad.tif")}, content_type="multipart/form-data")
    assert response.status_code == 422 and response.get_json()["error"]["code"] == "invalid_tiff"
    response = client.post("/api/v1/images", data={"file": (io.BytesIO(b"not tiff"), "bad.png")}, content_type="multipart/form-data")
    assert response.status_code == 415
    missing = client.get("/api/v1/images/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404 and missing.get_json()["error"]["code"] == "image_not_found"


def test_previews_reuse_the_local_copy_but_recheck_access(client, hestia, uploaded_image):
    image_id = uploaded_image["image_id"]
    assert client.get(f"/api/v1/images/{image_id}/channels/0/preview").status_code == 200
    assert client.get(f"/api/v1/images/{image_id}/channels/1/preview").status_code == 200
    assert hestia.calls.count(f"download {image_id}") == 1
    hestia.capabilities[TOKEN]["images_read"] = False
    denied = client.get(f"/api/v1/images/{image_id}/channels/0/preview")
    assert denied.status_code == 403 and denied.get_json()["error"]["code"] == "forbidden"


def test_image_routes_require_a_hestia_login(anonymous_client, uploaded_image):
    for path in ("/api/v1/images", f"/api/v1/images/{uploaded_image['image_id']}", f"/api/v1/images/{uploaded_image['image_id']}/channels/0/preview"):
        response = anonymous_client.get(path)
        assert response.status_code == 401 and response.get_json()["error"]["code"] == "unauthenticated"


def test_cleanup_keeps_cached_images_referenced_by_live_annotations(app, client, annotation, uploaded_image):
    store = app.extensions["mulan_store"]
    cached = store.resource_dir("images", uploaded_image["image_id"])
    old = time.time() - 48 * 3600
    os.utime(cached, (old, old))
    assert client.post("/api/internal/v1/cleanup").status_code == 200
    assert cached.is_dir()
    os.utime(store.resource_dir("annotations", annotation["annotation_id"]), (old, old))
    result = client.post("/api/internal/v1/cleanup")
    assert result.status_code == 200 and result.get_json()["removed"] == 2
    assert not cached.exists()
    # The local copy is only a cache: HESTIA still serves the image.
    assert client.get(f"/api/v1/images/{uploaded_image['image_id']}/channels/0/preview").status_code == 200
