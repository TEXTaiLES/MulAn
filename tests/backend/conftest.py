from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from fake_hestia import TOKEN, FakeHestia
from mulan import create_app


@pytest.fixture()
def hestia():
    return FakeHestia()


@pytest.fixture()
def app(tmp_path, hestia):
    app = create_app({"TESTING": True, "MULAN_DATA_DIR": str(tmp_path / "data"), "MAX_CONTENT_LENGTH": 20 * 1024 * 1024, "HESTIA_PORTAL_URL": "http://portal.test"})
    app.extensions["hestia"] = hestia
    return app


@pytest.fixture()
def anonymous_client(app):
    return app.test_client()


@pytest.fixture()
def client(app):
    """A client signed in to HESTIA as user-1."""
    signed_in = app.test_client()
    signed_in.set_cookie(app.config["HESTIA_COOKIE_NAME"], TOKEN)
    return signed_in


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



def annotation_package(mask: np.ndarray, classes: list[dict]) -> bytes:
    """A MulAn v1 annotation package, as HESTIA stores and serves it."""
    metadata = {
        "format": "mulan-semantic-segmentation", "version": "1.0",
        "image": {"width": mask.shape[1], "height": mask.shape[0]},
        "mask": {"filename": "mask.tif", "dtype": str(mask.dtype), "background_id": 0, "ignore_id": None},
        "classes": classes,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mask.tif", tiff(mask, "mask.tif")[0].getvalue())
        archive.writestr("annotations.json", json.dumps(metadata))
    return buffer.getvalue()
