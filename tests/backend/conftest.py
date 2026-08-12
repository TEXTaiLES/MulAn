from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from mulan import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "MULAN_DATA_DIR": str(tmp_path / "data"), "MAX_CONTENT_LENGTH": 20 * 1024 * 1024})


@pytest.fixture()
def client(app):
    return app.test_client()


def bmp(array: np.ndarray, mode: str | None = None, name: str = "band.bmp") -> tuple[io.BytesIO, str]:
    buffer = io.BytesIO()
    Image.fromarray(array, mode=mode).save(buffer, "BMP")
    buffer.seek(0)
    return buffer, name


def tiff(data: np.ndarray, name: str = "image.tif", *, crs=None, transform=None, dtype=None, descriptions=None) -> tuple[io.BytesIO, str]:
    if data.ndim == 2:
        data = data[np.newaxis, ...]
    dtype = dtype or data.dtype
    profile = {"driver": "GTiff", "width": data.shape[2], "height": data.shape[1], "count": data.shape[0], "dtype": dtype}
    if crs:
        profile["crs"] = crs
        profile["transform"] = transform or from_origin(0, 10, 1, 1)
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(data.astype(dtype))
            for index, description in enumerate(descriptions or [], 1):
                if description:
                    dataset.set_band_description(index, description)
        payload = io.BytesIO(memory.read())
    return payload, name


@pytest.fixture()
def uploaded_image(client):
    data = np.stack([np.arange(120, dtype=np.uint16).reshape(10, 12), np.full((10, 12), 500, np.uint16)])
    response = client.post("/api/v1/images", data={"file": tiff(data, descriptions=["450nm", "850nm"])}, content_type="multipart/form-data")
    assert response.status_code == 201
    return response.get_json()


@pytest.fixture()
def annotation(client, uploaded_image):
    response = client.post("/api/v1/annotations", data={"image_id": uploaded_image["image_id"]})
    assert response.status_code == 201
    return response.get_json()


def add_class(client, annotation_id, name="Class one", color="#ff0000"):
    response = client.post(f"/api/v1/annotations/{annotation_id}/classes", json={"name": name, "description": "", "color": color})
    assert response.status_code == 201
    return response.get_json()


def operation(client, annotation_id, revision, tool, class_id, points, radius=None):
    payload = {"base_revision": revision, "tool": tool, "class_id": class_id, "points": points}
    if radius is not None:
        payload["radius"] = radius
    return client.post(f"/api/internal/v1/annotations/{annotation_id}/operations", json=payload)

