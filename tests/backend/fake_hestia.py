"""In-memory stand-in for HESTIA's MulAn endpoints, mirroring their rules."""

from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

import rasterio
from rasterio.errors import RasterioIOError

from mulan.errors import ApiError


ALL_CAPABILITIES = ("images_read", "images_create", "annotations_read", "annotations_create", "annotations_update")
TOKEN = "valid-token"
OTHER_TOKEN = "other-token"


class FakeHestia:
    def __init__(self):
        self.users = {
            TOKEN: {"id": "user-1", "email": "ada@example.com", "display_name": "Ada Lovelace"},
            OTHER_TOKEN: {"id": "user-2", "email": "bob@example.com", "display_name": "Bob"},
        }
        self.capabilities = {token: {cap: True for cap in ALL_CAPABILITIES} for token in self.users}
        self.calls: list[str] = []
        self.images: dict[str, dict] = {}
        self.files: dict[str, bytes] = {}
        self.annotations: dict[str, dict] = {}

    def _session_for(self, token: str | None) -> dict:
        if token not in self.users:
            raise ApiError("unauthenticated", "A HESTIA login is required.", 401)
        return {"user": self.users[token], "capabilities": self.capabilities[token]}

    def _require(self, token: str | None, *capabilities: str) -> dict:
        session = self._session_for(token)
        if not all(session["capabilities"][cap] for cap in capabilities):
            raise ApiError("forbidden", "You do not have permission for this action.", 403)
        return session

    def session(self, token: str | None) -> dict:
        self.calls.append("session")
        if token not in self.users:
            return {"authenticated": False, "user": None, "capabilities": {cap: False for cap in ALL_CAPABILITIES}}
        return {"authenticated": True, **self._session_for(token)}

    def _image(self, image_id: str) -> dict:
        try:
            image_id = str(uuid.UUID(image_id))
        except ValueError:
            raise ApiError("invalid_image_id", "The image id must be a UUID.", 400)
        if image_id not in self.images:
            raise ApiError("image_not_found", "No such multispectral image.", 404)
        return {**self.images[image_id], "has_annotation": image_id in self.annotations}

    def list_images(self, token: str | None, params: dict) -> dict:
        self._require(token, "images_read")
        self.calls.append(f"list_images {sorted(params.items())}")
        items = [self._image(image_id) for image_id in self.images]
        return {"items": items, "page": int(params.get("page", 1)), "per_page": int(params.get("per_page", 50)), "total": len(items)}

    def image(self, token: str | None, image_id: str) -> dict:
        self._require(token, "images_read")
        self.calls.append(f"image {image_id}")
        return self._image(image_id)

    def open_image_file(self, token: str | None, image_id: str) -> FakeFileResponse:
        image = self.image(token, image_id)
        data = self.files[image["image_id"]]
        return FakeFileResponse(data, {"Content-Type": "image/tiff", "Content-Length": str(len(data)), "Content-Disposition": f"attachment; filename={image['filename']}"})

    def download_image(self, token: str | None, image_id: str, target: Path) -> None:
        self.calls.append(f"download {image_id}")
        with self.open_image_file(token, image_id) as response, target.open("wb") as output:
            shutil.copyfileobj(response.raw, output)

    def upload_image(self, token: str | None, source: BinaryIO, filename: str) -> dict:
        session = self._require(token, "images_create")
        if not filename.lower().endswith((".tif", ".tiff")):
            raise ApiError("unsupported_media_type", "Only .tif and .tiff files are accepted.", 415)
        data = source.read()
        try:
            with rasterio.MemoryFile(data) as memory, memory.open() as dataset:
                if dataset.driver != "GTiff":
                    raise ApiError("invalid_tiff", "The file is not a supported multiband TIFF.", 422)
                dtypes = set(dataset.dtypes)
                details = {
                    "width": dataset.width, "height": dataset.height, "channel_count": dataset.count,
                    "dtype": next(iter(dtypes)) if len(dtypes) == 1 else "mixed",
                    "channel_names": list(dataset.descriptions), "georeferenced": dataset.crs is not None,
                }
        except RasterioIOError:
            raise ApiError("invalid_tiff", "The file is not a readable TIFF.", 422)
        image_id = str(uuid.uuid4())
        self.images[image_id] = {
            "image_id": image_id, "filename": filename, **details, "size_bytes": len(data),
            "annotation_updated_at": None, "created_at": "2026-10-22T10:00:00Z",
            "created_by": {"id": session["user"]["id"], "display_name": session["user"]["display_name"]},
            "file_url": f"/api/v1/multispectral/images/{image_id}/file",
        }
        self.files[image_id] = data
        return self._image(image_id)


    def _annotation_body(self, image_id: str) -> dict:
        stored = self.annotations[image_id]
        image = self.images[image_id]
        return {
            "annotation_id": stored["annotation_id"], "multispectral_image_id": image_id,
            "format": "mulan-semantic-segmentation", "format_version": "1.0", "revision": stored["revision"],
            "classes": stored["metadata"]["classes"],
            "mask": {"width": image["width"], "height": image["height"], "dtype": stored["mask_dtype"], "background_id": 0, "ignore_id": None},
            "created_at": "2026-10-22T10:00:00Z", "updated_at": "2026-10-22T10:00:00Z",
            "package_url": f"/api/v1/multispectral/images/{image_id}/annotation/package",
        }

    def annotation(self, token: str | None, image_id: str) -> dict | None:
        self._require(token, "images_read", "annotations_read")
        image_id = self._image(image_id)["image_id"]
        self.calls.append(f"annotation {image_id}")
        return self._annotation_body(image_id) if image_id in self.annotations else None

    def annotation_package(self, token: str | None, image_id: str) -> bytes:
        self._require(token, "images_read", "annotations_read")
        image_id = self._image(image_id)["image_id"]
        if image_id not in self.annotations:
            raise ApiError("annotation_not_found", "This image has no annotation.", 404)
        stored = self.annotations[image_id]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("mask.tif", stored["mask"])
            archive.writestr("annotations.json", json.dumps(stored["metadata"]))
        return buffer.getvalue()

    def save_annotation(self, token: str | None, image_id: str, package: bytes, *, overwrite: bool, expected_revision: int | None) -> dict:
        session = self._require(token, "images_read")
        caps = session["capabilities"]
        if not (caps["annotations_create"] or caps["annotations_update"]):
            raise ApiError("forbidden", "You do not have permission for this action.", 403)
        image = self._image(image_id)
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            if sorted(archive.namelist()) != ["annotations.json", "mask.tif"]:
                raise ApiError("invalid_annotation_package", "The ZIP must contain exactly mask.tif and annotations.json at its root.", 422)
            mask = archive.read("mask.tif")
            metadata = json.loads(archive.read("annotations.json"))
        with rasterio.MemoryFile(mask) as memory, memory.open() as dataset:
            if (dataset.width, dataset.height) != (image["width"], image["height"]):
                raise ApiError("mask_dimension_mismatch", "mask.tif dimensions differ from the image.", 422)
            mask_dtype = dataset.dtypes[0]
        if not any(item["id"] == 0 and item["name"] == "Background" for item in metadata["classes"]):
            raise ApiError("invalid_annotation_package", "annotations.json is not a valid MulAn v1 file.", 422)
        current = self.annotations.get(image["image_id"])
        if not caps["annotations_update" if current else "annotations_create"]:
            raise ApiError("forbidden", "You do not have permission for this action.", 403)
        if current:
            details = {"annotation_id": current["annotation_id"], "revision": current["revision"]}
            if not overwrite:
                raise ApiError("annotation_exists", "This image already has an annotation.", 409, details)
            if expected_revision is not None and expected_revision != current["revision"]:
                raise ApiError("annotation_revision_conflict", "The annotation changed since you last loaded it.", 409, details)
        self.calls.append(f"save_annotation {image['image_id']} overwrite={overwrite} expected={expected_revision}")
        self.annotations[image["image_id"]] = {
            "annotation_id": current["annotation_id"] if current else str(uuid.uuid4()),
            "revision": current["revision"] + 1 if current else 1,
            "mask": mask, "mask_dtype": mask_dtype, "metadata": metadata,
        }
        return self._annotation_body(image["image_id"])


class FakeFileResponse:
    def __init__(self, data: bytes, headers: dict[str, str]):
        self.raw = io.BytesIO(data)
        self.headers = headers
        self.closed = False

    def iter_content(self, chunk_size: int):
        while chunk := self.raw.read(chunk_size):
            yield chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
