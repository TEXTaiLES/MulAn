from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..errors import ApiError
from ..hestia import HestiaClient
from ..storage.filesystem import FileStore
from .images import ImageService, inspect_tiff


class HestiaImageCache:
    """Local copies of HESTIA images, kept so MulAn can render previews and build masks.

    HESTIA stays the source of truth: every lookup first asks HESTIA for the
    image, which also checks that the caller may read it. HESTIA images are
    immutable, so a cached copy under the same image ID never goes stale.
    """

    def __init__(self, store: FileStore, client: HestiaClient):
        self.store = store
        self.client = client
        self.images = ImageService(store)

    def ensure(self, token: str, image_id: str) -> dict:
        """HESTIA's metadata for the image, after making sure a local copy exists."""
        metadata = self.client.image(token, image_id)
        image_id = metadata["image_id"]
        try:
            self.images.path(image_id)
            self.images.get(image_id)
        except ApiError:
            self._download(token, image_id, metadata["filename"])
        return metadata

    def path(self, token: str, image_id: str) -> Path:
        return self.images.path(self.ensure(token, image_id)["image_id"])

    def _download(self, token: str, image_id: str, filename: str) -> None:
        target = self.store.resource_dir("images", image_id, must_exist=False)
        # Build the copy in a scratch directory and move it into place in one
        # step, so concurrent requests never see a half-written image.
        _, scratch = self.store.create("conversions")
        try:
            self.client.download_image(token, image_id, scratch / "source.tif")
            details = inspect_tiff(scratch / "source.tif")
            self.store.write_json("conversions", scratch.name, {"image_id": image_id, "filename": self.store.safe_filename(filename, "image.tif"), **details})
            if target.exists():
                shutil.rmtree(target)
            try:
                os.rename(scratch, target)
            except OSError:
                if not target.is_dir():
                    raise
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
