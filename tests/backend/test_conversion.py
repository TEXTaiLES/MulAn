from __future__ import annotations

import io
import json

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
    rgb = np.stack([np.full((4, 4), 11, np.uint8), np.full((4, 4), 22, np.uint8), np.full((4, 4), 33, np.uint8)], axis=2)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(rgb, "RGB", "color.bmp")], "response_mode": "resource", "output_name": "safe.tif"}, content_type="multipart/form-data")
    assert response.status_code == 201
    result = response.get_json()
    assert result["channel_count"] == 3
    assert result["channel_names"] == ["color:R", "color:G", "color:B"]
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


def test_single_rgb_expands_to_rgb_bands(client):
    color = np.stack([
        np.arange(20, dtype=np.uint8).reshape(4, 5),
        np.full((4, 5), 101, np.uint8),
        np.flipud(np.arange(20, dtype=np.uint8).reshape(4, 5)),
    ], axis=2)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": bmp(color, "RGB", "scene.bmp")}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert response.headers["X-Channel-Count"] == "3"
    with MemoryFile(response.data) as memory, memory.open() as dataset:
        assert dataset.count == 3
        np.testing.assert_array_equal(dataset.read(), np.moveaxis(color, 2, 0))
        assert dataset.descriptions == ("scene:R", "scene:G", "scene:B")


def test_grayscale_rgb_grayscale_expands_in_file_and_component_order(client):
    gray_first = np.full((3, 4), 7, np.uint8)
    color = np.stack([np.full((3, 4), value, np.uint8) for value in (31, 47, 89)], axis=2)
    gray_last = np.full((3, 4), 211, np.uint8)
    names = ["gray1", "red", "green", "blue", "gray2"]
    response = client.post("/api/v1/convert/bmp-to-tiff", data={
        "files": [bmp(gray_first, name="gray1.bmp"), bmp(color, "RGB", "rgb.bmp"), bmp(gray_last, name="gray2.bmp")],
        "channel_names": json.dumps(names),
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    with MemoryFile(response.data) as memory, memory.open() as dataset:
        expected = np.stack([gray_first, color[..., 0], color[..., 1], color[..., 2], gray_last])
        assert dataset.count == 5
        np.testing.assert_array_equal(dataset.read(), expected)
        assert dataset.descriptions == tuple(names)


def test_multiple_rgb_files_remain_grouped(client):
    first = np.stack([np.full((2, 3), value, np.uint8) for value in (1, 2, 3)], axis=2)
    second = np.stack([np.full((2, 3), value, np.uint8) for value in (4, 5, 6)], axis=2)
    response = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(first, "RGB", "first.bmp"), bmp(second, "RGB", "second.bmp")]}, content_type="multipart/form-data")
    assert response.status_code == 200
    with MemoryFile(response.data) as memory, memory.open() as dataset:
        np.testing.assert_array_equal(dataset.read(), np.moveaxis(np.concatenate([first, second], axis=2), 2, 0))
        assert dataset.descriptions == ("first:R", "first:G", "first:B", "second:R", "second:G", "second:B")


def test_rgb_dimension_mismatch_and_expanded_channel_name_count(client):
    color = np.zeros((3, 5, 3), np.uint8)
    mismatch = client.post("/api/v1/convert/bmp-to-tiff", data={"files": [bmp(np.zeros((4, 5), np.uint8), name="gray.bmp"), bmp(color, "RGB", "color.bmp")]}, content_type="multipart/form-data")
    assert mismatch.status_code == 422
    assert mismatch.get_json()["error"] == {
        "code": "dimension_mismatch",
        "message": "All BMP images must have identical dimensions.",
        "details": {"file": "color.bmp", "expected": [5, 4], "received": [5, 3]},
    }
    bad_names = client.post("/api/v1/convert/bmp-to-tiff", data={"files": bmp(color, "RGB", "color.bmp"), "channel_names": '["color"]'}, content_type="multipart/form-data")
    assert bad_names.status_code == 422
    assert bad_names.get_json()["error"]["details"]["expected"] == 3


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
