from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file

from ..auth import hestia, require_login, require_session, require_token
from ..errors import ApiError
from ..services.annotations import AnnotationService
from ..services.hestia_annotations import HestiaAnnotationService


internal_api = Blueprint("internal_api", __name__)
internal_api.before_request(require_login)


def _owned(annotation_id: str) -> AnnotationService:
    """The annotation service, once the caller is known to own the working copy."""
    store = current_app.extensions["mulan_store"]
    HestiaAnnotationService(store, hestia()).authorize(require_session()["user"]["id"], annotation_id)
    return AnnotationService(store)


@internal_api.post("/annotations/<annotation_id>/operations")
def operation(annotation_id: str):
    return jsonify(_owned(annotation_id).apply_operation(annotation_id, request.get_json(silent=True)))


@internal_api.post("/annotations/<annotation_id>/undo")
def undo(annotation_id: str):
    return jsonify(_owned(annotation_id).undo(annotation_id))


@internal_api.post("/annotations/<annotation_id>/redo")
def redo(annotation_id: str):
    return jsonify(_owned(annotation_id).redo(annotation_id))


@internal_api.post("/annotations/<annotation_id>/save")
def save(annotation_id: str):
    """Writes the working copy to HESTIA."""
    store = current_app.extensions["mulan_store"]
    session = require_session()
    return jsonify(HestiaAnnotationService(store, hestia()).save(require_token(), session["user"]["id"], annotation_id))


@internal_api.patch("/annotations/<annotation_id>/class-order")
def class_order(annotation_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("class_ids"), list) or any(not isinstance(value, int) for value in payload["class_ids"]):
        raise ApiError("invalid_class_order", "class_ids must be an array of integers.", 422)
    return jsonify({"classes": _owned(annotation_id).reorder_classes(annotation_id, payload["class_ids"])})


@internal_api.get("/annotations/<annotation_id>/overlay")
def overlay(annotation_id: str):
    try:
        max_size = int(request.args.get("max_size", "1600"))
    except ValueError as exc:
        raise ApiError("invalid_max_size", "max_size must be an integer.", 400) from exc
    if max_size < 32 or max_size > 4096:
        raise ApiError("invalid_max_size", "max_size must be between 32 and 4096.", 400)
    visible_ids = None
    if "visible_ids" in request.args:
        try:
            visible_ids = {int(value) for value in request.args["visible_ids"].split(",") if value}
        except ValueError as exc:
            raise ApiError("invalid_visible_ids", "visible_ids must be comma-separated integers.", 400) from exc
    return send_file(_owned(annotation_id).overlay(annotation_id, max_size, visible_ids), mimetype="image/png")


@internal_api.post("/cleanup")
def cleanup():
    store = current_app.extensions["mulan_store"]
    removed = store.cleanup_expired(float(current_app.config["MULAN_RESOURCE_TTL_HOURS"]))
    return jsonify({"removed": removed})

