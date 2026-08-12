from __future__ import annotations

import io

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from conftest import bmp


def test_bmp_order_and_descriptions(client):
    first = np.full((5, 7), 17, np.uint8); second = np.full((5, 7), 93, np.uint8)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(first, name="first.bmp"), bmp(second, name="second.bmp")], "channel_names": '["450nm","850nm"]'}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert response.headers["X-Channel-Count"] == "2"
    with MemoryFile(response.data) as memory, memory.open() as dataset:
        assert dataset.count == 2
        np.testing.assert_array_equal(dataset.read(1), first)
        np.testing.assert_array_equal(dataset.read(2), second)
        assert dataset.descriptions == ("450nm", "850nm")
        assert dataset.crs is None


def test_resource_conversion(client):
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(np.ones((4, 4), np.uint8))], "response_mode": "resource", "output_name": "safe.tif"}, content_type="multipart/form-data")
    assert response.status_code == 201
    result = response.get_json()
    assert result["channel_count"] == 1
    assert client.get(result["download_url"]).status_code == 200


def test_conversion_rejections(client):
    missing = client.post("/api/v1/convert/bmp-to-tiff")
    assert missing.status_code == 400
    wrong_ext = client.post("/api/v1/convert/bmp-to-tiff", data={"files": (io.BytesIO(b"x"), "x.png")}, content_type="multipart/form-data")
    assert wrong_ext.status_code == 415
    mismatch = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(np.zeros((4, 5), np.uint8), name="a.bmp"), bmp(np.zeros((3, 5), np.uint8), name="b.bmp")]}, content_type="multipart/form-data")
    assert mismatch.status_code == 422
    assert mismatch.get_json()["error"]["code"] == "dimension_mismatch"
    bad_names = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(np.zeros((4, 5), np.uint8))], "channel_names": "[]"}, content_type="multipart/form-data")
    assert bad_names.status_code == 422


def test_true_rgb_bmp_rejected_and_identical_rgb_accepted(client):
    color = np.zeros((4, 4, 3), np.uint8); color[..., 0] = 10; color[..., 1] = 20
    rejected = client.post("/api/v1/convert/bmp-to-tiff", data={"files": bmp(color, "RGB")}, content_type="multipart/form-data")
    assert rejected.status_code == 422
    assert rejected.get_json()["error"]["code"] == "color_bmp_not_supported"
    gray = np.repeat(np.arange(16, dtype=np.uint8).reshape(4, 4)[..., None], 3, axis=2)
    accepted = client.post("/api/v1/convert/bmp-to-tiff", data={"files": bmp(gray, "RGB")}, content_type="multipart/form-data")
    assert accepted.status_code == 200


def test_color_palette_bmp_rejected(client):
    from PIL import Image
    palette_image = Image.fromarray(np.array([[0, 1], [1, 0]], dtype=np.uint8), mode="P")
    palette = [0, 0, 0, 255, 0, 0] + [0, 0, 0] * 254
    palette_image.putpalette(palette)
    payload = io.BytesIO(); palette_image.save(payload, "BMP"); payload.seek(0)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": (payload, "palette.bmp")}, content_type="multipart/form-data")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "color_bmp_not_supported"


def test_unused_color_palette_entries_do_not_make_grayscale_pixels_invalid(client):
    from PIL import Image
    palette_image = Image.fromarray(np.zeros((2, 2), dtype=np.uint8), mode="P")
    palette_image.putpalette([30, 30, 30, 255, 0, 0] + [0, 0, 0] * 254)
    payload = io.BytesIO(); palette_image.save(payload, "BMP"); payload.seek(0)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": (payload, "grayscale-pixels.bmp")}, content_type="multipart/form-data")
    assert response.status_code == 200
