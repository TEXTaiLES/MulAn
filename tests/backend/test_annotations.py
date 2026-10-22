from __future__ import annotations

import io
import json
import zipfile

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from conftest import add_class, annotation_package, operation, tiff
from fake_hestia import OTHER_TOKEN, TOKEN


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


def test_mask_apply_uses_shared_undo_redo_history(client, annotation):
    aid = annotation["annotation_id"]
    original_class = add_class(client, aid, "Original")
    revision = client.get(f"/api/v1/annotations/{aid}").get_json()["revision"]
    painted = operation(client, aid, revision, "rectangle_add", original_class["id"], [{"x": 1, "y": 1}, {"x": 4, "y": 4}])
    assert painted.status_code == 200
    original_mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))

    imported_mask = np.zeros((10, 12), np.uint16)
    imported_mask[5:8, 6:10] = 5
    applied = client.put(
        f"/api/v1/annotations/{aid}/mask",
        data={"mask": tiff(imported_mask, "mask.tif"), "overwrite": "true"},
        content_type="multipart/form-data",
    )
    assert applied.status_code == 200
    assert applied.get_json()["can_undo"] is True and applied.get_json()["can_redo"] is False
    assert [item["id"] for item in applied.get_json()["classes"]] == [0, 5]
    current_mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    np.testing.assert_array_equal(current_mask, imported_mask)

    undone = client.post(f"/api/internal/v1/annotations/{aid}/undo").get_json()
    assert undone["can_undo"] is True and undone["can_redo"] is True
    assert [item["id"] for item in undone["classes"]] == [0, original_class["id"]]
    restored_mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    np.testing.assert_array_equal(restored_mask, original_mask)

    redone = client.post(f"/api/internal/v1/annotations/{aid}/redo").get_json()
    assert [item["id"] for item in redone["classes"]] == [0, 5]
    redone_mask, _ = read_mask(client.get(f"/api/v1/annotations/{aid}/mask"))
    np.testing.assert_array_equal(redone_mask, imported_mask)

    undone_again = client.post(f"/api/internal/v1/annotations/{aid}/undo").get_json()
    edited = operation(client, aid, undone_again["revision"], "brush_add", original_class["id"], [{"x": 10, "y": 8}], radius=1)
    assert edited.status_code == 200 and edited.get_json()["can_redo"] is False
    assert client.post(f"/api/internal/v1/annotations/{aid}/redo").status_code == 409


def test_mask_metadata_conflict_rejected(client, annotation):
    aid = annotation["annotation_id"]
    metadata = io.BytesIO(json.dumps({"format": "mulan-semantic-segmentation", "version": "1.0", "image": {"width": 99, "height": 10}, "mask": {"background_id": 0, "ignore_id": None}, "classes": [{"id": 0, "name": "Background", "description": "", "color": "#000000"}]}).encode())
    response = client.put(f"/api/v1/annotations/{aid}/mask", data={"mask": tiff(np.zeros((10, 12), np.uint8), "mask.tif"), "metadata": (metadata, "annotations.json")}, content_type="multipart/form-data")
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "metadata_conflict"


def test_opening_an_image_loads_its_hestia_annotation(client, hestia, uploaded_image):
    image_id = uploaded_image["image_id"]
    stored_mask = np.zeros((10, 12), np.uint8); stored_mask[2:5, 3:7] = 4
    classes = [{"id": 0, "name": "Background", "description": "", "color": "#000000"}, {"id": 4, "name": "Thread", "description": "warp", "color": "#43A047"}]
    hestia.save_annotation(TOKEN, image_id, annotation_package(stored_mask, classes), overwrite=False, expected_revision=None)
    opened = client.post("/api/v1/annotations", data={"image_id": image_id})
    assert opened.status_code == 201
    body = opened.get_json()
    assert body["hestia_revision"] == 1 and body["revision"] == body["saved_revision"] == 0
    assert [(item["id"], item["name"]) for item in body["classes"]] == [(0, "Background"), (4, "Thread")]
    assert "_hestia" not in body
    mask, _ = read_mask(client.get(f"/api/v1/annotations/{body['annotation_id']}/mask"))
    np.testing.assert_array_equal(mask, stored_mask)
    # The next class continues after the highest stored ID.
    assert add_class(client, body["annotation_id"], "Weft")["id"] == 5


def test_opening_an_unannotated_image_starts_blank(annotation):
    assert annotation["hestia_revision"] is None
    assert [item["id"] for item in annotation["classes"]] == [0]


def test_opening_requires_image_id_and_annotation_read_access(client, hestia, uploaded_image):
    assert client.post("/api/v1/annotations").status_code == 400
    hestia.capabilities[TOKEN]["annotations_read"] = False
    denied = client.post("/api/v1/annotations", data={"image_id": uploaded_image["image_id"]})
    assert denied.status_code == 403 and denied.get_json()["error"]["code"] == "forbidden"


def test_working_copies_belong_to_the_user_who_opened_them(app, annotation):
    other = app.test_client()
    other.set_cookie(app.config["HESTIA_COOKIE_NAME"], OTHER_TOKEN)
    aid = annotation["annotation_id"]
    for response in (
        other.get(f"/api/v1/annotations/{aid}"),
        other.post(f"/api/v1/annotations/{aid}/classes", json={"name": "Intruder", "color": "#ff0000"}),
        other.post(f"/api/internal/v1/annotations/{aid}/undo"),
        other.get(f"/api/internal/v1/annotations/{aid}/overlay"),
    ):
        assert response.status_code == 404 and response.get_json()["error"]["code"] == "annotation_not_found"


def save(client, annotation_id):
    return client.post(f"/api/internal/v1/annotations/{annotation_id}/save")


def paint(client, annotation_id, class_id, points):
    revision = client.get(f"/api/v1/annotations/{annotation_id}").get_json()["revision"]
    response = operation(client, annotation_id, revision, "rectangle_add", class_id, points)
    assert response.status_code == 200
    return response.get_json()


def test_save_writes_the_package_to_hestia_and_exports_come_from_hestia(client, hestia, annotation, uploaded_image):
    aid = annotation["annotation_id"]; image_id = uploaded_image["image_id"]; cls = add_class(client, aid)
    paint(client, aid, cls["id"], [{"x": 1, "y": 1}, {"x": 4, "y": 4}])
    saved = save(client, aid)
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["revision"] == body["saved_revision"] and body["hestia_revision"] == 1
    assert f"save_annotation {image_id} overwrite=False expected=None" in hestia.calls
    stored = hestia.annotations[image_id]
    assert [item["id"] for item in stored["metadata"]["classes"]] == [0, cls["id"]]
    with MemoryFile(stored["mask"]) as memory, memory.open() as dataset:
        assert dataset.read(1)[2, 2] == cls["id"] and dataset.dtypes[0] == "uint8"
    assert client.get(f"/api/v1/annotations/{aid}").get_json()["hestia_revision"] == 1

    exported = client.get(f"/api/v1/images/{image_id}/annotation/package?include_image=true")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.data)) as package:
        assert set(package.namelist()) == {"image.tif", "mask.tif", "annotations.json"}
        metadata = json.loads(package.read("annotations.json"))
        assert metadata["format"] == "mulan-semantic-segmentation" and metadata["mask"]["background_id"] == 0
        assert package.read("mask.tif") == stored["mask"]
        assert package.read("image.tif") == client.get(f"/api/v1/images/{image_id}/file").data
    mask_only = client.get(f"/api/v1/images/{image_id}/annotation/package")
    with zipfile.ZipFile(io.BytesIO(mask_only.data)) as package:
        assert set(package.namelist()) == {"mask.tif", "annotations.json"}

    overlay = client.get(f"/api/internal/v1/annotations/{aid}/overlay?max_size=100")
    assert overlay.status_code == 200 and overlay.content_type == "image/png"


def test_later_saves_update_the_hestia_revision_they_started_from(client, hestia, annotation, uploaded_image):
    aid = annotation["annotation_id"]; image_id = uploaded_image["image_id"]; cls = add_class(client, aid)
    paint(client, aid, cls["id"], [{"x": 1, "y": 1}, {"x": 2, "y": 2}])
    assert save(client, aid).get_json()["hestia_revision"] == 1
    paint(client, aid, cls["id"], [{"x": 5, "y": 5}, {"x": 6, "y": 6}])
    assert save(client, aid).get_json()["hestia_revision"] == 2
    assert f"save_annotation {image_id} overwrite=True expected=1" in hestia.calls
    # Saving again without changes does not create another HESTIA revision.
    assert save(client, aid).get_json()["hestia_revision"] == 2 and hestia.annotations[image_id]["revision"] == 2


def test_save_refuses_to_overwrite_newer_hestia_edits(app, client, hestia, uploaded_image):
    image_id = uploaded_image["image_id"]
    mine = client.post("/api/v1/annotations", data={"image_id": image_id}).get_json()
    other = app.test_client(); other.set_cookie(app.config["HESTIA_COOKIE_NAME"], OTHER_TOKEN)
    theirs = other.post("/api/v1/annotations", data={"image_id": image_id}).get_json()
    for user, working_copy in ((other, theirs), (client, mine)):
        cls = add_class(user, working_copy["annotation_id"])
        paint(user, working_copy["annotation_id"], cls["id"], [{"x": 1, "y": 1}, {"x": 3, "y": 3}])
    assert save(other, theirs["annotation_id"]).status_code == 200
    conflict = save(client, mine["annotation_id"])
    assert conflict.status_code == 409 and conflict.get_json()["error"]["code"] == "annotation_exists"
    assert "Reopen the image" in conflict.get_json()["error"]["message"]
    still_unsaved = client.get(f"/api/v1/annotations/{mine['annotation_id']}").get_json()
    assert still_unsaved["revision"] != still_unsaved["saved_revision"]

    reopened = client.post("/api/v1/annotations", data={"image_id": image_id}).get_json()
    assert reopened["hestia_revision"] == 1
    other_copy = other.post("/api/v1/annotations", data={"image_id": image_id}).get_json()
    cls = add_class(other, other_copy["annotation_id"], "Later")
    paint(other, other_copy["annotation_id"], cls["id"], [{"x": 6, "y": 6}, {"x": 7, "y": 7}])
    assert save(other, other_copy["annotation_id"]).status_code == 200
    paint(client, reopened["annotation_id"], reopened["classes"][-1]["id"], [{"x": 8, "y": 8}, {"x": 9, "y": 9}])
    stale = save(client, reopened["annotation_id"])
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "annotation_revision_conflict"


def test_save_needs_the_matching_hestia_capability(client, hestia, annotation):
    aid = annotation["annotation_id"]; cls = add_class(client, aid)
    paint(client, aid, cls["id"], [{"x": 1, "y": 1}, {"x": 2, "y": 2}])
    hestia.capabilities[TOKEN]["annotations_create"] = False
    denied = save(client, aid)
    assert denied.status_code == 403 and denied.get_json()["error"]["code"] == "forbidden"


def test_background_class_cannot_be_renamed(client, annotation):
    aid = annotation["annotation_id"]
    renamed = client.patch(f"/api/v1/annotations/{aid}/classes/0", json={"name": "Canvas"})
    assert renamed.status_code == 409 and renamed.get_json()["error"]["code"] == "background_rename_forbidden"
    assert client.patch(f"/api/v1/annotations/{aid}/classes/0", json={"color": "#111111"}).status_code == 200


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
