from __future__ import annotations

import io
import zipfile

from werkzeug.datastructures import FileStorage

from ..errors import ApiError
from ..hestia import HestiaClient
from ..storage.filesystem import FileStore
from .annotations import AnnotationService
from .hestia_images import HestiaImageCache


class HestiaAnnotationService:
    """Editing sessions over the annotations HESTIA stores.

    Opening an image copies its HESTIA annotation (or a blank mask) into a
    local working copy. Drawing, undo/redo, and class edits change only that
    copy; saving writes it back to HESTIA. Each working copy belongs to the
    HESTIA user who opened it.
    """

    def __init__(self, store: FileStore, client: HestiaClient):
        self.store = store
        self.client = client
        self.images = HestiaImageCache(store, client)
        self.annotations = AnnotationService(store)

    def open(self, token: str, user_id: str, image_id: str) -> dict:
        image_id = self.images.ensure(token, image_id)["image_id"]
        stored = self.client.annotation(token, image_id)
        package = None
        if stored is not None:
            package = FileStorage(io.BytesIO(self.client.annotation_package(token, image_id)), filename="annotation.zip")
        annotation_id = self.annotations.create(image_id, package)["annotation_id"]
        metadata = self.store.read_json("annotations", annotation_id)
        metadata["_hestia"] = {"owner": user_id, "revision": stored["revision"] if stored else None}
        self.store.write_json("annotations", annotation_id, metadata)
        return self.get(user_id, annotation_id)

    def authorize(self, user_id: str, annotation_id: str) -> dict:
        """The working copy's HESTIA link, if ``user_id`` opened it."""
        metadata = self.store.read_json("annotations", annotation_id)
        link = metadata.get("_hestia")
        if not isinstance(link, dict) or link.get("owner") != user_id:
            raise ApiError("annotation_not_found", "The requested annotation was not found.", 404)
        return link

    def get(self, user_id: str, annotation_id: str) -> dict:
        link = self.authorize(user_id, annotation_id)
        return {**self.annotations.get(annotation_id), "hestia_revision": link["revision"]}

    def save(self, token: str, user_id: str, annotation_id: str) -> dict:
        """Writes the working copy to HESTIA, refusing to overwrite newer HESTIA edits."""
        link = self.authorize(user_id, annotation_id)
        revision = self.annotations.check_saveable(annotation_id)
        metadata = self.store.read_json("annotations", annotation_id)
        if link["revision"] is not None and metadata["saved_revision"] == revision:
            return {"revision": revision, "saved_revision": revision, "hestia_revision": link["revision"]}
        image_id = metadata["image_id"]
        package = self.annotations.export_zip(annotation_id, include_image=False).getvalue()
        try:
            stored = self.client.save_annotation(token, image_id, package, overwrite=link["revision"] is not None, expected_revision=link["revision"])
        except ApiError as error:
            if error.code in {"annotation_exists", "annotation_revision_conflict"}:
                raise ApiError(error.code, "This annotation was changed in HESTIA after you opened it. Reopen the image to load the latest version.", 409, error.details) from error
            raise
        metadata = self.store.read_json("annotations", annotation_id)
        metadata["_hestia"] = {**link, "revision": stored["revision"]}
        self.store.write_json("annotations", annotation_id, metadata)
        return {**self.annotations.save(annotation_id, revision), "hestia_revision": stored["revision"]}

    def package(self, token: str, image_id: str, include_image: bool) -> io.BytesIO:
        """The image's annotation package as stored in HESTIA, optionally with the source TIFF."""
        package = self.client.annotation_package(token, image_id)
        if not include_image:
            return io.BytesIO(package)
        image_path = self.images.path(token, image_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(package)) as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in source.infolist():
                archive.writestr(entry.filename, source.read(entry))
            archive.write(image_path, "image.tif")
        buffer.seek(0)
        return buffer
