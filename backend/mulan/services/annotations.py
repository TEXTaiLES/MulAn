from __future__ import annotations

import io
import json
import math
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image, ImageColor, ImageDraw
from rasterio.errors import RasterioIOError
from rasterio.enums import Resampling
from werkzeug.datastructures import FileStorage

from ..errors import ApiError
from ..storage.filesystem import FileStore
from .images import ImageService, TIFF_EXTENSIONS


DEFAULT_CLASS = {"id": 0, "name": "Background", "description": "", "color": "#000000", "order": 0}
MAX_CLASS_ID = 65535
TOOLS = {"brush_add", "erase", "lasso_add", "lasso_subtract", "rectangle_add", "rectangle_subtract"}


def _validate_color(color: Any) -> str:
    if not isinstance(color, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        raise ApiError("invalid_class", "Class color must be a hexadecimal color.", 422)
    try:
        ImageColor.getrgb(color)
    except ValueError as exc:
        raise ApiError("invalid_class", "Class color must be a valid color.", 422) from exc
    return color


def _normalize_class(item: dict, *, require_id: bool = True, order: int = 0) -> dict:
    if not isinstance(item, dict):
        raise ApiError("invalid_class", "Each class must be an object.", 422)
    class_id = item.get("id")
    if require_id and (not isinstance(class_id, int) or isinstance(class_id, bool) or class_id < 0 or class_id > MAX_CLASS_ID):
        raise ApiError("invalid_class_id", "Class IDs must be integers from 0 to 65535.", 422)
    name = item.get("name", f"Class {class_id}")
    description = item.get("description", "")
    if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
        raise ApiError("invalid_class", "Class name must be non-empty and description must be text.", 422)
    return {
        "id": class_id,
        "name": name.strip(),
        "description": description,
        "color": _validate_color(item.get("color", "#E53935")),
        "order": item.get("order", order) if isinstance(item.get("order", order), int) else order,
    }


def _metadata_classes(payload: Any, mask_ids: set[int]) -> list[dict]:
    if payload is None:
        classes = [dict(DEFAULT_CLASS)]
    else:
        if not isinstance(payload, dict) or not isinstance(payload.get("classes"), list):
            raise ApiError("invalid_metadata", "Annotation metadata must contain a classes array.", 422)
        classes = [_normalize_class(item, order=index) for index, item in enumerate(payload["classes"])]
        ids = [item["id"] for item in classes]
        if len(ids) != len(set(ids)):
            raise ApiError("invalid_metadata", "Class IDs in metadata must be unique.", 422)
        background = next((item for item in classes if item["id"] == 0), None)
        if background is None:
            raise ApiError("invalid_metadata", "Annotation metadata must define Background class 0.", 422)
    known = {item["id"] for item in classes}
    palette = ["#E53935", "#43A047", "#1E88E5", "#FB8C00", "#8E24AA", "#00ACC1"]
    for class_id in sorted(mask_ids - known):
        classes.append({"id": class_id, "name": f"Class {class_id}", "description": "", "color": palette[class_id % len(palette)], "order": len(classes)})
    return classes


class AnnotationService:
    def __init__(self, store: FileStore):
        self.store = store
        self.images = ImageService(store)

    def _dir(self, annotation_id: str) -> Path:
        return self.store.resource_dir("annotations", annotation_id)

    def _mask_path(self, annotation_id: str) -> Path:
        return self._dir(annotation_id) / "mask.npy"

    def _load_mask(self, annotation_id: str) -> np.ndarray:
        try:
            mask = np.load(self._mask_path(annotation_id), allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ApiError("resource_corrupt", "The stored annotation mask is unreadable.", 500) from exc
        if mask.ndim != 2 or mask.dtype != np.uint16:
            raise ApiError("resource_corrupt", "The stored annotation mask is invalid.", 500)
        return mask

    def _save_mask(self, annotation_id: str, mask: np.ndarray) -> None:
        path = self._mask_path(annotation_id)
        temp = path.with_suffix(".tmp.npy")
        np.save(temp, mask.astype(np.uint16, copy=False), allow_pickle=False)
        temp.replace(path)

    def _load_import_metadata(self, upload: FileStorage | None) -> dict | None:
        if upload is None or not upload.filename:
            return None
        if Path(upload.filename).suffix.lower() != ".json":
            raise ApiError("unsupported_metadata", "Metadata must be an annotations.json file.", 415)
        try:
            upload.stream.seek(0)
            data = json.load(upload.stream)
        except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            raise ApiError("invalid_metadata", "Annotation metadata is not valid JSON.", 422) from exc
        return data

    def _read_import(self, mask_upload: FileStorage, metadata_upload: FileStorage | None, expected_width: int, expected_height: int) -> tuple[np.ndarray, list[dict]]:
        if not mask_upload or not mask_upload.filename:
            raise ApiError("missing_mask", "A mask TIFF is required.", 400)
        extension = Path(mask_upload.filename).suffix.lower()
        temp_dir = self.store.root / "conversions" / str(uuid.uuid4())
        temp_dir.mkdir()
        try:
            mask_path = temp_dir / "mask.tif"
            metadata_payload = self._load_import_metadata(metadata_upload)
            if extension == ".zip":
                mask_upload.stream.seek(0)
                try:
                    with zipfile.ZipFile(mask_upload.stream) as archive:
                        names = {Path(name).name: name for name in archive.namelist() if not name.endswith("/")}
                        mask_name = next((original for base, original in names.items() if base.lower() in {"mask.tif", "mask.tiff"}), None)
                        if mask_name is None:
                            raise ApiError("invalid_mask_package", "The ZIP must contain mask.tif.", 422)
                        mask_path.write_bytes(archive.read(mask_name))
                        if metadata_payload is None:
                            json_name = next((original for base, original in names.items() if base.lower() == "annotations.json"), None)
                            if json_name:
                                metadata_payload = json.loads(archive.read(json_name).decode("utf-8"))
                except ApiError:
                    raise
                except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
                    raise ApiError("invalid_mask_package", "The mask ZIP package is unreadable.", 422) from exc
            elif extension in TIFF_EXTENSIONS:
                mask_upload.save(mask_path)
            else:
                raise ApiError("unsupported_media_type", "Mask must be a .tif, .tiff, or supported .zip package.", 415)
            if metadata_payload is not None:
                if metadata_payload.get("format", "mulan-semantic-segmentation") != "mulan-semantic-segmentation" or str(metadata_payload.get("version", "1.0")) != "1.0":
                    raise ApiError("invalid_metadata", "Annotation metadata format and version are not supported.", 422)
                mask_metadata = metadata_payload.get("mask", {})
                if not isinstance(mask_metadata, dict) or mask_metadata.get("background_id", 0) != 0 or mask_metadata.get("ignore_id") is not None:
                    raise ApiError("metadata_conflict", "Metadata must use background_id 0 and ignore_id null for MulAn v1.", 422)
                image_metadata = metadata_payload.get("image", {})
                if not isinstance(image_metadata, dict):
                    raise ApiError("invalid_metadata", "Metadata image information must be an object.", 422)
                if image_metadata.get("width", expected_width) != expected_width or image_metadata.get("height", expected_height) != expected_height:
                    raise ApiError("metadata_conflict", "Metadata image dimensions conflict with the source image.", 422)
            try:
                with rasterio.open(mask_path) as source:
                    if source.driver != "GTiff":
                        raise ApiError("invalid_mask", "The mask file is not a TIFF container.", 422)
                    if source.count != 1:
                        raise ApiError("invalid_mask_bands", "The mask TIFF must contain exactly one raster band.", 422, {"received": source.count})
                    if source.width != expected_width or source.height != expected_height:
                        raise ApiError("mask_dimension_mismatch", "Mask dimensions must match the source image.", 422, {"expected": [expected_width, expected_height], "received": [source.width, source.height]})
                    dtype = np.dtype(source.dtypes[0])
                    if not np.issubdtype(dtype, np.integer):
                        raise ApiError("invalid_mask_dtype", "The mask TIFF must use an integer datatype.", 422, {"received": str(dtype)})
                    array = source.read(1)
            except ApiError:
                raise
            except (RasterioIOError, ValueError, OSError) as exc:
                raise ApiError("invalid_mask", "The mask is not a readable TIFF raster.", 422) from exc
            if np.issubdtype(array.dtype, np.signedinteger) and int(array.min(initial=0)) < 0:
                raise ApiError("negative_class_id", "Mask class IDs cannot be negative.", 422)
            maximum = int(array.max(initial=0))
            if maximum > MAX_CLASS_ID:
                raise ApiError("class_id_too_large", "Mask class IDs cannot exceed 65535 in v1.", 422)
            mask = array.astype(np.uint16)
            ids = {int(value) for value in np.unique(mask)}
            classes = _metadata_classes(metadata_payload, ids)
            return mask, classes
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def create(self, image_id: str, mask_upload: FileStorage | None = None, metadata_upload: FileStorage | None = None, *, owns_image: bool = False) -> dict:
        image = self.images.get(image_id)
        annotation_id, directory = self.store.create("annotations")
        try:
            if mask_upload and mask_upload.filename:
                mask, classes = self._read_import(mask_upload, metadata_upload, image["width"], image["height"])
            else:
                if metadata_upload and metadata_upload.filename:
                    raise ApiError("metadata_without_mask", "Metadata can only be supplied with a mask.", 400)
                mask = np.zeros((image["height"], image["width"]), dtype=np.uint16)
                classes = [dict(DEFAULT_CLASS)]
            np.save(directory / "mask.npy", mask, allow_pickle=False)
            metadata = {
                "annotation_id": annotation_id,
                "image_id": image_id,
                "filename": image["filename"],
                "width": image["width"],
                "height": image["height"],
                "channel_count": image["channel_count"],
                "revision": 0,
                "saved_revision": 0,
                "classes": classes,
                "next_class_id": max(item["id"] for item in classes) + 1,
                "_owns_image": owns_image,
            }
            self.store.write_json("annotations", annotation_id, metadata)
            self.store.write_json("annotations", annotation_id, {"undo": [], "redo": []}, "history.json")
            (directory / "history").mkdir()
            return self.get(annotation_id)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def get(self, annotation_id: str, statistics: bool = True) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        result = {key: value for key, value in metadata.items() if key not in {"next_class_id", "_owns_image"}}
        if statistics:
            mask = self._load_mask(annotation_id)
            values, counts = np.unique(mask, return_counts=True)
            count_map = {int(value): int(count) for value, count in zip(values, counts, strict=True)}
            result["mask_dtype"] = "uint16"
            result["statistics"] = [{"class_id": item["id"], "pixel_count": count_map.get(item["id"], 0)} for item in result["classes"]]
        history = self.store.read_json("annotations", annotation_id, "history.json")
        result["can_undo"] = bool(history["undo"])
        result["can_redo"] = bool(history["redo"])
        return result

    def _save_metadata(self, annotation_id: str, metadata: dict) -> None:
        self.store.write_json("annotations", annotation_id, metadata)

    def add_class(self, annotation_id: str, payload: dict) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        next_id = metadata["next_class_id"]
        if next_id > MAX_CLASS_ID:
            raise ApiError("class_limit", "No additional classes can be created.", 422)
        data = dict(payload or {})
        data["id"] = next_id
        item = _normalize_class(data, order=len(metadata["classes"]))
        metadata["classes"].append(item)
        metadata["next_class_id"] = next_id + 1
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        return item

    def update_class(self, annotation_id: str, class_id: int, payload: dict) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        current = next((item for item in metadata["classes"] if item["id"] == class_id), None)
        if current is None:
            raise ApiError("class_not_found", "The requested class does not exist.", 404)
        allowed = {"name", "description", "color", "order"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ApiError("invalid_class", "Only name, description, color, and order can be edited.", 422)
        updated = _normalize_class({**current, **payload}, order=current.get("order", 0))
        updated["id"] = class_id
        metadata["classes"][metadata["classes"].index(current)] = updated
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        return updated

    def reorder_classes(self, annotation_id: str, class_ids: list[int]) -> list[dict]:
        metadata = self.store.read_json("annotations", annotation_id)
        existing = {item["id"]: item for item in metadata["classes"]}
        if len(class_ids) != len(existing) or set(class_ids) != set(existing):
            raise ApiError("invalid_class_order", "Class order must contain every existing class ID exactly once.", 422)
        metadata["classes"] = [{**existing[class_id], "order": index} for index, class_id in enumerate(class_ids)]
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        return metadata["classes"]

    def delete_class(self, annotation_id: str, class_id: int) -> None:
        if class_id == 0:
            raise ApiError("background_delete_forbidden", "Background class 0 cannot be deleted.", 409)
        metadata = self.store.read_json("annotations", annotation_id)
        if not any(item["id"] == class_id for item in metadata["classes"]):
            raise ApiError("class_not_found", "The requested class does not exist.", 404)
        mask = self._load_mask(annotation_id)
        mask[mask == class_id] = 0
        self._save_mask(annotation_id, mask)
        metadata["classes"] = [item for item in metadata["classes"] if item["id"] != class_id]
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        self._clear_history(annotation_id)

    def replace_mask(self, annotation_id: str, mask_upload: FileStorage, metadata_upload: FileStorage | None, overwrite: bool) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        current = self._load_mask(annotation_id)
        meaningful = bool(np.any(current)) or len(metadata["classes"]) > 1
        if meaningful and not overwrite:
            raise ApiError("overwrite_required", "The current annotation contains edits; explicit overwrite is required.", 409)
        mask, classes = self._read_import(mask_upload, metadata_upload, metadata["width"], metadata["height"])
        self._save_mask(annotation_id, mask)
        metadata["classes"] = classes
        metadata["next_class_id"] = max(item["id"] for item in classes) + 1
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        self._clear_history(annotation_id)
        return self.get(annotation_id)

    def _clear_history(self, annotation_id: str) -> None:
        history_dir = self._dir(annotation_id) / "history"
        if history_dir.exists():
            for file in history_dir.glob("*.npz"):
                file.unlink(missing_ok=True)
        self.store.write_json("annotations", annotation_id, {"undo": [], "redo": []}, "history.json")

    @staticmethod
    def _points(payload: dict, minimum: int) -> list[tuple[float, float]]:
        raw = payload.get("points")
        if not isinstance(raw, list) or len(raw) < minimum:
            raise ApiError("invalid_operation", f"This operation requires at least {minimum} point(s).", 422)
        points = []
        for point in raw:
            if not isinstance(point, dict) or not isinstance(point.get("x"), (int, float)) or not isinstance(point.get("y"), (int, float)):
                raise ApiError("invalid_operation", "Operation points require numeric x and y coordinates.", 422)
            x, y = float(point["x"]), float(point["y"])
            if not math.isfinite(x) or not math.isfinite(y):
                raise ApiError("invalid_operation", "Operation coordinates must be finite.", 422)
            points.append((x, y))
        return points

    def apply_operation(self, annotation_id: str, payload: dict) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        if not isinstance(payload, dict):
            raise ApiError("invalid_operation", "The operation body must be a JSON object.", 400)
        if payload.get("base_revision") != metadata["revision"]:
            raise ApiError("revision_conflict", "The annotation changed since this operation was prepared.", 409, {"current_revision": metadata["revision"]})
        tool = payload.get("tool")
        if tool not in TOOLS:
            raise ApiError("invalid_tool", "The requested annotation tool is not supported.", 422)
        class_id = payload.get("class_id")
        if not isinstance(class_id, int) or not any(item["id"] == class_id for item in metadata["classes"]):
            raise ApiError("class_not_found", "The active class does not exist.", 422)
        if class_id == 0:
            raise ApiError("invalid_active_class", "Background cannot be used as an active drawing class.", 422)
        minimum = 3 if tool.startswith("lasso") else (2 if tool.startswith("rectangle") else 1)
        points = self._points(payload, minimum)
        mask = self._load_mask(annotation_id)
        selection_image = Image.new("1", (metadata["width"], metadata["height"]), 0)
        draw = ImageDraw.Draw(selection_image)
        rounded = [(round(x), round(y)) for x, y in points]
        if tool in {"brush_add", "erase"}:
            radius = payload.get("radius", 1)
            if not isinstance(radius, (int, float)) or not math.isfinite(float(radius)) or radius <= 0 or radius > max(metadata["width"], metadata["height"]):
                raise ApiError("invalid_radius", "Brush radius must be a positive finite number within the image extent.", 422)
            width = max(1, round(float(radius) * 2))
            if len(rounded) > 1:
                draw.line(rounded, fill=1, width=width, joint="curve")
            for x, y in rounded:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=1)
        elif tool.startswith("lasso"):
            draw.polygon(rounded, fill=1)
        else:
            (x1, y1), (x2, y2) = rounded[0], rounded[-1]
            draw.rectangle((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), fill=1)
        selection = np.asarray(selection_image, dtype=bool)
        old_mask = mask.copy()
        if tool.endswith("add"):
            mask[selection] = class_id
        else:
            mask[selection & (mask == class_id)] = 0
        changed = mask != old_mask
        if np.any(changed):
            ys, xs = np.nonzero(changed)
            y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
            self._record_patch(annotation_id, (x0, y0, x1, y1), old_mask[y0:y1, x0:x1], mask[y0:y1, x0:x1])
            self._save_mask(annotation_id, mask)
            metadata["revision"] += 1
            self._save_metadata(annotation_id, metadata)
        else:
            history = self.store.read_json("annotations", annotation_id, "history.json")
            if history["redo"]:
                directory = self._dir(annotation_id) / "history"
                for entry in history["redo"]:
                    (directory / entry).unlink(missing_ok=True)
                history["redo"] = []
                self.store.write_json("annotations", annotation_id, history, "history.json")
        history = self.store.read_json("annotations", annotation_id, "history.json")
        return {"revision": metadata["revision"], "saved_revision": metadata["saved_revision"], "can_undo": bool(history["undo"]), "can_redo": bool(history["redo"])}

    def _record_patch(self, annotation_id: str, bbox: tuple[int, int, int, int], old: np.ndarray, new: np.ndarray) -> None:
        history = self.store.read_json("annotations", annotation_id, "history.json")
        directory = self._dir(annotation_id) / "history"
        for entry in history["redo"]:
            (directory / entry).unlink(missing_ok=True)
        filename = f"{uuid.uuid4()}.npz"
        np.savez_compressed(directory / filename, bbox=np.asarray(bbox, dtype=np.int32), old=old, new=new)
        history["redo"] = []
        history["undo"].append(filename)
        while len(history["undo"]) > 50:
            (directory / history["undo"].pop(0)).unlink(missing_ok=True)
        self.store.write_json("annotations", annotation_id, history, "history.json")

    def _history_action(self, annotation_id: str, direction: str) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        history = self.store.read_json("annotations", annotation_id, "history.json")
        source = history[direction]
        if not source:
            raise ApiError(f"nothing_to_{direction}", f"There is nothing to {direction}.", 409)
        filename = source.pop()
        try:
            with np.load(self._dir(annotation_id) / "history" / filename, allow_pickle=False) as patch:
                x0, y0, x1, y1 = (int(value) for value in patch["bbox"])
                values = patch["old"] if direction == "undo" else patch["new"]
                mask = self._load_mask(annotation_id)
                mask[y0:y1, x0:x1] = values
        except (OSError, ValueError, KeyError) as exc:
            raise ApiError("history_corrupt", "Annotation history is unreadable.", 500) from exc
        self._save_mask(annotation_id, mask)
        target = "redo" if direction == "undo" else "undo"
        history[target].append(filename)
        metadata["revision"] += 1
        self._save_metadata(annotation_id, metadata)
        self.store.write_json("annotations", annotation_id, history, "history.json")
        return {"revision": metadata["revision"], "saved_revision": metadata["saved_revision"], "can_undo": bool(history["undo"]), "can_redo": bool(history["redo"])}

    def undo(self, annotation_id: str) -> dict:
        return self._history_action(annotation_id, "undo")

    def redo(self, annotation_id: str) -> dict:
        return self._history_action(annotation_id, "redo")

    def save(self, annotation_id: str) -> dict:
        metadata = self.store.read_json("annotations", annotation_id)
        mask = self._load_mask(annotation_id)
        known = {item["id"] for item in metadata["classes"]}
        actual = {int(value) for value in np.unique(mask)}
        if not actual.issubset(known):
            raise ApiError("unknown_mask_class", "The mask contains class IDs missing from annotation metadata.", 422, {"class_ids": sorted(actual - known)})
        metadata["saved_revision"] = metadata["revision"]
        self._save_metadata(annotation_id, metadata)
        return {"revision": metadata["revision"], "saved_revision": metadata["saved_revision"]}

    def export_mask(self, annotation_id: str) -> Path:
        metadata = self.store.read_json("annotations", annotation_id)
        mask = self._load_mask(annotation_id)
        maximum = int(mask.max(initial=0))
        dtype = "uint8" if maximum <= 255 else "uint16"
        target = self._dir(annotation_id) / f"mask-r{metadata['revision']}.tif"
        if target.exists():
            return target
        image_path = self.images.path(metadata["image_id"])
        with rasterio.open(image_path) as source:
            profile = {"driver": "GTiff", "width": source.width, "height": source.height, "count": 1, "dtype": dtype}
            if source.crs is not None:
                profile["crs"] = source.crs
                profile["transform"] = source.transform
            with rasterio.open(target, "w", **profile) as output:
                output.write(mask.astype(dtype), 1)
                output.set_band_description(1, "Semantic class ID")
                output.update_tags(MULAN_FORMAT="mulan-semantic-segmentation", MULAN_VERSION="1.0", BACKGROUND_ID="0")
        return target

    def annotation_json(self, annotation_id: str) -> dict:
        annotation = self.store.read_json("annotations", annotation_id)
        image = self.images.get(annotation["image_id"])
        mask = self._load_mask(annotation_id)
        dtype = "uint8" if int(mask.max(initial=0)) <= 255 else "uint16"
        classes = [{key: item[key] for key in ("id", "name", "description", "color")} for item in annotation["classes"]]
        return {
            "format": "mulan-semantic-segmentation",
            "version": "1.0",
            "image": {"filename": image["filename"], "width": image["width"], "height": image["height"], "channels": image["channel_count"], "channel_names": image["channel_names"]},
            "mask": {"filename": "mask.tif", "dtype": dtype, "background_id": 0, "ignore_id": None},
            "classes": classes,
        }

    def export_zip(self, annotation_id: str, include_image: bool) -> io.BytesIO:
        buffer = io.BytesIO()
        mask_path = self.export_mask(annotation_id)
        metadata = self.store.read_json("annotations", annotation_id)
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(mask_path, "mask.tif")
            archive.writestr("annotations.json", json.dumps(self.annotation_json(annotation_id), indent=2))
            if include_image:
                archive.write(self.images.path(metadata["image_id"]), "image.tif")
        buffer.seek(0)
        return buffer

    def overlay(self, annotation_id: str, max_size: int, visible_ids: set[int] | None = None) -> io.BytesIO:
        metadata = self.store.read_json("annotations", annotation_id)
        mask = self._load_mask(annotation_id)
        scale = min(1.0, max_size / max(metadata["width"], metadata["height"]))
        size = (max(1, round(metadata["width"] * scale)), max(1, round(metadata["height"] * scale)))
        if size != (metadata["width"], metadata["height"]):
            mask = np.asarray(Image.fromarray(mask).resize(size, Image.Resampling.NEAREST))
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        for item in metadata["classes"]:
            class_id = item["id"]
            if class_id == 0 or (visible_ids is not None and class_id not in visible_ids):
                continue
            pixels = mask == class_id
            rgba[pixels, :3] = ImageColor.getrgb(item["color"])
            rgba[pixels, 3] = 130
        buffer = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    def delete(self, annotation_id: str) -> None:
        metadata = self.store.read_json("annotations", annotation_id)
        self.store.delete("annotations", annotation_id)
        if metadata.get("_owns_image"):
            try:
                self.images.delete(metadata["image_id"])
            except ApiError as error:
                if error.code != "image_in_use":
                    raise
