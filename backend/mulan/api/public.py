from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from ..errors import ApiError
from ..services.annotations import AnnotationService
from ..services.conversion import convert_bmps, parse_channel_names, parse_manifest, prepare_bmps
from ..services.images import ImageService


public_api = Blueprint("public_api", __name__)


def _services() -> tuple[ImageService, AnnotationService]:
    store = current_app.extensions["mulan_store"]
    return ImageService(store), AnnotationService(store)


def _bool_field(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = value.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ApiError("invalid_boolean", "Boolean fields must be true or false.", 400)


@public_api.post("/images")
def upload_image():
    images, _ = _services()
    metadata = images.create_from_upload(request.files.get("file"))
    return jsonify(metadata), 201


@public_api.get("/images/<image_id>")
def image_metadata(image_id: str):
    images, _ = _services()
    return jsonify(images.get(image_id))


@public_api.get("/images/<image_id>/file")
def image_file(image_id: str):
    images, _ = _services()
    metadata = images.get(image_id)
    return send_file(images.path(image_id), mimetype="image/tiff", as_attachment=True, download_name=metadata["filename"], conditional=True)


@public_api.get("/images/<image_id>/channels/<int:channel_index>/preview")
def channel_preview(image_id: str, channel_index: int):
    images, _ = _services()
    try:
        max_size = int(request.args.get("max_size", "1600"))
    except ValueError as exc:
        raise ApiError("invalid_max_size", "max_size must be an integer.", 400) from exc
    path = images.preview(image_id, channel_index, max_size, request.args.get("normalization", "percentile"))
    return send_file(path, mimetype="image/png", conditional=True, max_age=3600)


@public_api.delete("/images/<image_id>")
def delete_image(image_id: str):
    images, _ = _services()
    images.delete(image_id)
    return "", 204


@public_api.post("/convert/bmp-to-tiff")
def bmp_to_tiff():
    files = request.files.getlist("files")
    if not files or not any(item.filename for item in files):
        raise ApiError("missing_files", "At least one BMP file is required.", 400)
    inputs = prepare_bmps(files)
    output_count = sum(input_bmp.count for input_bmp in inputs)
    names = parse_channel_names(request.form.get("channel_names"), output_count)
    manifest_names = parse_manifest(request.form.get("manifest"), files, [input_bmp.count for input_bmp in inputs])
    if manifest_names is not None:
        if request.form.get("channel_names") not in (None, "") and names != manifest_names:
            raise ApiError("manifest_conflict", "channel_names and manifest describe different names.", 422)
        names = manifest_names
    response_mode = request.form.get("response_mode", "direct")
    if response_mode not in {"direct", "resource"}:
        raise ApiError("invalid_response_mode", "response_mode must be direct or resource.", 400)
    output_name = current_app.extensions["mulan_store"].safe_filename(request.form.get("output_name", "multispectral.tif"), "multispectral.tif")
    if Path(output_name).suffix.lower() not in {".tif", ".tiff"}:
        output_name = f"{Path(output_name).stem or 'multispectral'}.tif"
    with tempfile.TemporaryDirectory(prefix="mulan-convert-") as temporary:
        output_path = Path(temporary) / "output.tif"
        result = convert_bmps(inputs, output_path, names)
        if response_mode == "direct":
            data = io.BytesIO(output_path.read_bytes())
            response = send_file(data, mimetype="image/tiff", as_attachment=True, download_name=output_name)
            response.headers["X-Channel-Count"] = str(result.count)
            return response
        images, _ = _services()
        metadata = images.create_from_existing_path(output_path, output_name)
    payload = {
        "image_id": metadata["image_id"], "filename": metadata["filename"], "width": metadata["width"],
        "height": metadata["height"], "channel_count": metadata["channel_count"], "channel_names": metadata["channel_names"],
        "download_url": f"/api/v1/images/{metadata['image_id']}/file",
    }
    return jsonify(payload), 201


@public_api.post("/annotations")
def create_annotation():
    images, annotations = _services()
    image_upload = request.files.get("image")
    image_id = request.form.get("image_id")
    if bool(image_upload and image_upload.filename) == bool(image_id):
        raise ApiError("invalid_image_source", "Provide exactly one of image or image_id.", 400)
    created_image_id = None
    if image_upload and image_upload.filename:
        image_meta = images.create_from_upload(image_upload)
        image_id = created_image_id = image_meta["image_id"]
    try:
        result = annotations.create(image_id, request.files.get("mask"), request.files.get("metadata"), owns_image=created_image_id is not None)
    except Exception:
        if created_image_id:
            images.delete(created_image_id)
        raise
    return jsonify(result), 201


@public_api.get("/annotations/<annotation_id>")
def get_annotation(annotation_id: str):
    _, annotations = _services()
    return jsonify(annotations.get(annotation_id))


@public_api.get("/annotations/<annotation_id>/mask")
def get_mask(annotation_id: str):
    _, annotations = _services()
    return send_file(annotations.export_mask(annotation_id), mimetype="image/tiff", as_attachment=True, download_name="mask.tif", conditional=True)


@public_api.put("/annotations/<annotation_id>/mask")
def replace_mask(annotation_id: str):
    _, annotations = _services()
    result = annotations.replace_mask(annotation_id, request.files.get("mask"), request.files.get("metadata"), _bool_field(request.form.get("overwrite")))
    return jsonify(result)


@public_api.post("/annotations/<annotation_id>/classes")
def add_class(annotation_id: str):
    _, annotations = _services()
    item = annotations.add_class(annotation_id, request.get_json(silent=True) or {})
    return jsonify(item), 201


@public_api.patch("/annotations/<annotation_id>/classes/<int:class_id>")
def update_class(annotation_id: str, class_id: int):
    _, annotations = _services()
    return jsonify(annotations.update_class(annotation_id, class_id, request.get_json(silent=True) or {}))


@public_api.delete("/annotations/<annotation_id>/classes/<int:class_id>")
def delete_class(annotation_id: str, class_id: int):
    _, annotations = _services()
    annotations.delete_class(annotation_id, class_id)
    return "", 204


@public_api.get("/annotations/<annotation_id>/export")
def export_annotation(annotation_id: str):
    _, annotations = _services()
    include_image = _bool_field(request.args.get("include_image"), False)
    return send_file(annotations.export_zip(annotation_id, include_image), mimetype="application/zip", as_attachment=True, download_name="annotation.zip" if include_image else "annotation-mask.zip")


@public_api.delete("/annotations/<annotation_id>")
def delete_annotation(annotation_id: str):
    _, annotations = _services()
    annotations.delete(annotation_id)
    return "", 204
