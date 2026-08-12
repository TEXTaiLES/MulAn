from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from conftest import add_class, operation, tiff


def read_mask(response):
    assert response.status_code == 200
    with MemoryFile(response.data) as memory, memory.open() as dataset:
        return dataset.read(1), dataset.profile


def test_annotation_creation_and_class_ids(client, annotation):
    aid = annotation["annotation_id"]
    assert "visible" not in annotation["classes"][0]
    one = add_class(client, aid, "One"); two = add_class(client, aid, "Two"); three = add_class(client, aid, "Three")
    assert [one["id"], two["id"], three["id"]] == [1, 2, 3]
    reordered = client.patch(f"/api/internal/v1/annotations/{aid}/class-order", json={"class_ids": [0, 3, 1, 2]})
    assert [item["id"] for item in reordered.get_json()["classes"]] == [0, 3, 1, 2]
    assert client.delete(f"/api/v1/annotations/{aid}/classes/2").status_code == 204
    four = add_class(client, aid, "Four")
    assert four["id"] == 4
    assert client.delete(f"/api/v1/annotations/{aid}/classes/0").status_code == 409
    assert client.patch(f"/api/v1/annotations/{aid}/classes/{one['id']}", json={"visible": False}).status_code == 422


def test_latest_wins_eraser_and_rectangles(client, annotation):
    aid = annotation["annotation_id"]; first = add_class(client, aid, "First"); second = add_class(client, aid, "Second")
    revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    result = operation(client, aid, revision, "rectangle_add", first["id"], [{"x": 1, "y": 1}, {"x": 8, "y": 8}]).get_json()
    result = operation(client, aid, result["revision"], "rectangle_add", second["id"], [{"x": 4, "y": 4}, {"x": 10, "y": 9}]).get_json()
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    assert mask[2, 2] == first["id"] and mask[5, 5] == second["id"]
    result = operation(client, aid, result["revision"], "erase", first["id"], [{"x": 5, "y": 5}], radius=3).get_json()
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    assert mask[5, 5] == second["id"]
    result = operation(client, aid, result["revision"], "rectangle_subtract", second["id"], [{"x": 4, "y": 4}, {"x": 6, "y": 6}])
    assert result.status_code == 200
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    assert mask[5, 5] == 0


def test_lasso_brush_undo_redo_and_invalidation(client, annotation):
    aid = annotation["annotation_id"]; cls = add_class(client, aid); revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    add = operation(client, aid, revision, "lasso_add", cls["id"], [{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 5, "y": 8}])
    assert add.status_code == 200
    rev = add.get_json()["revision"]
    subtract = operation(client, aid, rev, "lasso_subtract", cls["id"], [{"x": 4, "y": 3}, {"x": 7, "y": 3}, {"x": 5, "y": 6}])
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask")); assert mask[2, 5] == cls["id"] and mask[4, 5] == 0
    assert client.post(f"/api/internal/v1/annotations/{aid}/undo").status_code == 200
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask")); assert mask[4, 5] == cls["id"]
    assert client.post(f"/api/internal/v1/annotations/{aid}/redo").status_code == 200
    undo = client.post(f"/api/internal/v1/annotations/{aid}/undo").get_json()
    brush = operation(client, aid, undo["revision"], "brush_add", cls["id"], [{"x": 11, "y": 9}], radius=1)
    assert brush.status_code == 200
    assert client.post(f"/api/internal/v1/annotations/{aid}/redo").status_code == 409


def test_noop_operation_after_undo_still_invalidates_redo(client, annotation):
    aid = annotation["annotation_id"]; cls = add_class(client, aid); revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    painted = operation(client, aid, revision, "rectangle_add", cls["id"], [{"x": 1, "y": 1}, {"x": 3, "y": 3}]).get_json()
    undone = client.post(f"/api/internal/v1/annotations/{aid}/undo").get_json()
    noop = operation(client, aid, undone["revision"], "rectangle_subtract", cls["id"], [{"x": 8, "y": 8}, {"x": 10, "y": 9}])
    assert noop.status_code == 200 and noop.get_json()["can_redo"] is False
    assert client.post(f"/api/internal/v1/annotations/{aid}/redo").status_code == 409


def test_stale_revision_rejected_and_delete_pixels(client, annotation):
    aid = annotation["annotation_id"]; cls = add_class(client, aid); revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    assert operation(client, aid, revision - 1, "brush_add", cls["id"], [{"x": 2, "y": 2}], radius=1).status_code == 409
    result = operation(client, aid, revision, "rectangle_add", cls["id"], [{"x": 0, "y": 0}, {"x": 5, "y": 5}]); assert result.status_code == 200
    assert client.delete(f"/api/v1/annotations/{aid}/classes/{cls['id']}").status_code == 204
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask")); assert not mask.any()


def test_mask_import_validation_and_placeholders(client, annotation):
    aid = annotation["annotation_id"]
    mismatch = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.zeros((9, 12), np.uint8), "mask.tif")}, content_type="multipart/form-data")
    assert mismatch.status_code == 422
    multiband = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.zeros((2, 10, 12), np.uint8), "mask.tif")}, content_type="multipart/form-data")
    assert multiband.status_code == 422
    floating = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.zeros((10, 12), np.float32), "mask.tif")}, content_type="multipart/form-data")
    assert floating.status_code == 422
    imported = np.zeros((10, 12), np.uint16); imported[2:5, 3:7] = 5
    good = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(imported, "mask.tif")}, content_type="multipart/form-data")
    assert good.status_code == 200 and any(item["id"] == 5 for item in good.get_json()["classes"])
    conflict = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.ones((10, 12), np.uint8), "mask.tif")}, content_type="multipart/form-data")
    assert conflict.status_code == 409
    overwritten = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.ones((10, 12), np.uint8), "mask.tif"), "overwrite": "true"}, content_type="multipart/form-data")
    assert overwritten.status_code == 200


def test_mask_metadata_conflict_rejected(client, annotation):
    aid = annotation["annotation_id"]
    metadata = io.BytesIO(json.dumps({"format": "mulan-semantic-segmentation", "version": "1.0", "image": {"width": 99, "height": 10}, "mask": {"background_id": 0, "ignore_id": None}, "classes": [{"id": 0, "name": "Background", "description": "", "color": "#000000"}]}).encode())
    response = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.zeros((10, 12), np.uint8), "mask.tif"), "metadata": (metadata, "annotations.json")}, content_type="multipart/form-data")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "metadata_conflict"


def test_direct_upload_annotation_owns_image(client):
    response = client.post("/api/v1/annotations", data={"image": tiff(np.zeros((5, 7), np.uint8), "direct.tif")}, content_type="multipart/form-data")
    assert response.status_code == 201
    created = response.get_json()
    assert client.delete(f"/api/v1/annotations/{created['annotation_id']}").status_code == 204
    assert client.get(f"/api/v1/images/{created['image_id']}").status_code == 404


def test_exports_json_zip_save_and_overlay(client, annotation, uploaded_image):
    aid = annotation["annotation_id"]; cls = add_class(client, aid); revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    result = operation(client, aid, revision, "rectangle_add", cls["id"], [{"x": 1, "y": 1}, {"x": 4, "y": 4}]); assert result.status_code == 200
    saved = client.post(f"/api/internal/v1/annotations/{aid}/save").get_json(); assert saved["revision"] == saved["saved_revision"]
    overlay = client.get(f"/api/internal/v1/annotations/{aid}/overlay?max_size=100"); assert overlay.status_code == 200 and overlay.content_type == "image/png"
    exported = client.get(f"/api/v1/annotations/{aid}/export?include_image=true"); assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.data)) as package:
        assert set(package.namelist()) == {"image.tif", "mask.tif", "annotations.json"}
        metadata = json.loads(package.read("annotations.json"))
        assert metadata["format"] == "mulan-semantic-segmentation" and metadata["mask"]["background_id"] == 0
        assert package.read("image.tif") == client.get(f"/api/v1/images/{uploaded_image['image_id']}/file").data


def test_georeferencing_copied_and_not_invented(client):
    values = np.zeros((1, 5, 7), np.uint16); transform = from_origin(100, 200, 2, 2)
    source = client.post("/api/v1/images", data={"file": tiff(values, crs="EPSG:4326", transform=transform)}, content_type="multipart/form-data").get_json()
    annotation = client.post("/api/v1/annotations", data={"image_id": source["image_id"]}).get_json()
    with MemoryFile(client.get(f"/api/v1/annotations/{annotation['annotation_id']}/mask").data) as memory, memory.open() as mask:
        assert mask.crs.to_epsg() == 4326 and mask.transform == transform
    source2 = client.post("/api/v1/images", data={"file": tiff(values)}, content_type="multipart/form-data").get_json()
    annotation2 = client.post("/api/v1/annotations", data={"image_id": source2["image_id"]}).get_json()
    with MemoryFile(client.get(f"/api/v1/annotations/{annotation2['annotation_id']}/mask").data) as memory, memory.open() as mask:
        assert mask.crs is None
