from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, send_file, stream_with_context

from ..auth import hestia, require_login, require_session, require_token
from ..errors import ApiError
from ..services.annotations import AnnotationService
from ..services.conversion import convert_bmps, parse_channel_names, parse_manifest, prepare_bmps
from ..services.hestia_annotations import HestiaAnnotationService
from ..services.hestia_images import HestiaImageCache
from ..services.images import ImageService


public_api = Blueprint("public_api", __name__)
# MulAn is a HESTIA tool: every API call needs a signed-in HESTIA user.
public_api.before_request(require_login)

IMAGE_LIST_PARAMS = ("page", "per_page", "q", "sort", "has_annotation")
FORWARDED_FILE_HEADERS = ("Content-Type", "Content-Length", "Content-Disposition", "ETag", "Cache-Control")


def _services() -> tuple[ImageService, AnnotationService]:
    store = current_app.extensions["mulan_store"]
    return ImageService(store), AnnotationService(store)


def _image_cache() -> HestiaImageCache:
    return HestiaImageCache(current_app.extensions["mulan_store"], hestia())


def _hestia_annotations() -> HestiaAnnotationService:
    return HestiaAnnotationService(current_app.extensions["mulan_store"], hestia())


def _user_id() -> str:
    return require_session()["user"]["id"]


def _owned(annotation_id: str) -> AnnotationService:
    """The annotation service, once the caller is known to own the working copy."""
    _hestia_annotations().authorize(_user_id(), annotation_id)
    return _services()[1]


def _bool_field(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = value.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ApiError("invalid_boolean", "Boolean fields must be true or false.", 400)


@public_api.get("/images")
def list_images():
    params = {key: request.args[key] for key in IMAGE_LIST_PARAMS if key in request.args}
    return jsonify(hestia().list_images(require_token(), params))


@public_api.post("/images")
def upload_image():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        raise ApiError("missing_file", "A TIFF file is required.", 400)
    return jsonify(hestia().upload_image(require_token(), upload.stream, upload.filename)), 201


@public_api.get("/images/<image_id>")
def image_metadata(image_id: str):
    return jsonify(hestia().image(require_token(), image_id))


@public_api.get("/images/<image_id>/file")
def image_file(image_id: str):
    upstream = hestia().open_image_file(require_token(), image_id)
    headers = {name: upstream.headers[name] for name in FORWARDED_FILE_HEADERS if name in upstream.headers}

    def body():
        try:
            yield from upstream.iter_content(1024 * 1024)
        finally:
            upstream.close()

    return Response(stream_with_context(body()), headers=headers)


@public_api.get("/images/<image_id>/channels/<int:channel_index>/preview")
def channel_preview(image_id: str, channel_index: int):
    images, _ = _services()
    try:
        max_size = int(request.args.get("max_size", "1600"))
    except ValueError as exc:
        raise ApiError("invalid_max_size", "max_size must be an integer.", 400) from exc
    image_id = _image_cache().ensure(require_token(), image_id)["image_id"]
    path = images.preview(image_id, channel_index, max_size, request.args.get("normalization", "percentile"))
    response = send_file(path, mimetype="image/png", conditional=True, max_age=3600)
    response.cache_control.public = False
    response.cache_control.private = True
    return response


@public_api.get("/images/<image_id>/annotation/package")
def annotation_package(image_id: str):
    """The image's saved annotation from HESTIA, optionally bundled with the source TIFF."""
    include_image = _bool_field(request.args.get("include_image"), False)
    package = _hestia_annotations().package(require_token(), image_id, include_image)
    return send_file(package, mimetype="application/zip", as_attachment=True, download_name="annotation.zip" if include_image else "annotation-mask.zip")


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
        # "resource" mode stores the converted TIFF in HESTIA as a new image.
        with output_path.open("rb") as output:
            metadata = hestia().upload_image(require_token(), output, output_name)
    payload = {
        "image_id": metadata["image_id"], "filename": metadata["filename"], "width": metadata["width"],
        "height": metadata["height"], "channel_count": metadata["channel_count"], "channel_names": metadata["channel_names"],
        "download_url": f"/api/v1/images/{metadata['image_id']}/file",
    }
    return jsonify(payload), 201


@public_api.post("/annotations")
def create_annotation():
    """Opens a working copy of the image's HESTIA annotation (blank if it has none)."""
    image_id = request.form.get("image_id")
    if not image_id:
        raise ApiError("invalid_image_source", "image_id is required.", 400)
    return jsonify(_hestia_annotations().open(require_token(), _user_id(), image_id)), 201


@public_api.get("/annotations/<annotation_id>")
def get_annotation(annotation_id: str):
    return jsonify(_hestia_annotations().get(_user_id(), annotation_id))


@public_api.get("/annotations/<annotation_id>/mask")
def get_mask(annotation_id: str):
    return send_file(_owned(annotation_id).export_mask(annotation_id), mimetype="image/tiff", as_attachment=True, download_name="mask.tif", conditional=True)


@public_api.put("/annotations/<annotation_id>/mask")
def replace_mask(annotation_id: str):
    annotations = _owned(annotation_id)
    annotations.replace_mask(annotation_id, request.files.get("mask"), request.files.get("metadata"), _bool_field(request.form.get("overwrite")))
    return jsonify(_hestia_annotations().get(_user_id(), annotation_id))


@public_api.post("/annotations/<annotation_id>/classes")
def add_class(annotation_id: str):
    annotations = _owned(annotation_id)
    item = annotations.add_class(annotation_id, request.get_json(silent=True) or {})
    return jsonify(item), 201


@public_api.patch("/annotations/<annotation_id>/classes/<int:class_id>")
def update_class(annotation_id: str, class_id: int):
    annotations = _owned(annotation_id)
    return jsonify(annotations.update_class(annotation_id, class_id, request.get_json(silent=True) or {}))


@public_api.delete("/annotations/<annotation_id>/classes/<int:class_id>")
def delete_class(annotation_id: str, class_id: int):
    annotations = _owned(annotation_id)
    annotations.delete_class(annotation_id, class_id)
    return "", 204
