from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

from ..errors import ApiError


class FileStore:
    """Filesystem-backed resource store with UUID-owned paths."""

    KINDS = ("images", "annotations", "conversions")

    def __init__(self, root: Path):
        self.root = root.resolve()

    def initialize(self) -> None:
        for kind in self.KINDS:
            (self.root / kind).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def validate_id(resource_id: str) -> str:
        try:
            return str(uuid.UUID(resource_id))
        except (ValueError, AttributeError, TypeError):
            raise ApiError("resource_not_found", "The requested resource was not found.", 404)

    @staticmethod
    def safe_filename(filename: str, fallback: str) -> str:
        clean = secure_filename(Path(filename or "").name)
        return clean or fallback

    def resource_dir(self, kind: str, resource_id: str, must_exist: bool = True) -> Path:
        if kind not in self.KINDS:
            raise ValueError("Unknown resource kind")
        safe_id = self.validate_id(resource_id)
        path = (self.root / kind / safe_id).resolve()
        if self.root not in path.parents:
            raise ApiError("resource_not_found", "The requested resource was not found.", 404)
        if must_exist and not path.is_dir():
            singular = kind[:-1] if kind.endswith("s") else kind
            raise ApiError(f"{singular}_not_found", f"The requested {singular} was not found.", 404)
        return path

    def create(self, kind: str, resource_id: str | None = None) -> tuple[str, Path]:
        resource_id = resource_id or self.new_id()
        path = self.resource_dir(kind, resource_id, must_exist=False)
        path.mkdir(parents=False, exist_ok=False)
        return resource_id, path

    def read_json(self, kind: str, resource_id: str, filename: str = "metadata.json") -> dict[str, Any]:
        path = self.resource_dir(kind, resource_id) / filename
        if not path.is_file():
            raise ApiError("resource_not_found", "Resource metadata was not found.", 404)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ApiError("resource_corrupt", "Stored resource metadata is unreadable.", 500) from exc

    def write_json(self, kind: str, resource_id: str, data: dict[str, Any], filename: str = "metadata.json") -> None:
        path = self.resource_dir(kind, resource_id) / filename
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")
        os.replace(temp, path)

    def delete(self, kind: str, resource_id: str) -> None:
        path = self.resource_dir(kind, resource_id)
        shutil.rmtree(path)

    def cleanup_expired(self, ttl_hours: float) -> int:
        cutoff = time.time() - ttl_hours * 3600
        removed = 0
        # Expire annotations first, then retain any image still referenced by a
        # surviving annotation. This preserves the same safety guarantee as the
        # public image-delete endpoint.
        for candidate in list((self.root / "annotations").iterdir()):
            try:
                if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
                    shutil.rmtree(candidate)
                    removed += 1
            except FileNotFoundError:
                continue
        referenced_images: set[str] = set()
        for candidate in list((self.root / "annotations").iterdir()):
            try:
                metadata = json.loads((candidate / "metadata.json").read_text(encoding="utf-8"))
                if isinstance(metadata.get("image_id"), str):
                    referenced_images.add(metadata["image_id"])
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                continue
        for kind in ("images", "conversions"):
            for candidate in list((self.root / kind).iterdir()):
                try:
                    if kind == "images" and candidate.name in referenced_images:
                        continue
                    if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
                        shutil.rmtree(candidate)
                        removed += 1
                except FileNotFoundError:
                    continue
        return removed
