from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.errors import RasterioIOError
from rasterio.enums import Resampling
from werkzeug.datastructures import FileStorage

from ..errors import ApiError
from ..storage.filesystem import FileStore


TIFF_EXTENSIONS = {".tif", ".tiff"}


def _tiff_extension(filename: str) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in TIFF_EXTENSIONS:
        raise ApiError("unsupported_media_type", "Only .tif and .tiff files are supported.", 415, {"filename": filename})
    return extension


def inspect_tiff(path: Path) -> dict:
    try:
        with rasterio.open(path) as source:
            if source.driver != "GTiff":
                raise ApiError("invalid_tiff", "The uploaded file is not a TIFF container.", 422)
            if source.width <= 0 or source.height <= 0 or source.count < 1:
                raise ApiError("unsupported_tiff", "The TIFF does not contain a supported raster dataset.", 422)
            dtypes = list(source.dtypes)
            dtype = dtypes[0] if len(set(dtypes)) == 1 else "mixed"
            descriptions = [description if description else None for description in source.descriptions]
            return {
                "width": source.width,
                "height": source.height,
                "channel_count": source.count,
                "dtype": dtype,
                "channel_names": descriptions,
                "georeferenced": source.crs is not None,
            }
    except ApiError:
        raise
    except (RasterioIOError, ValueError, OSError) as exc:
        raise ApiError("invalid_tiff", "The uploaded file is not a readable TIFF raster.", 422) from exc


class ImageService:
    def __init__(self, store: FileStore):
        self.store = store

    def create_from_upload(self, upload: FileStorage) -> dict:
        if not upload or not upload.filename:
            raise ApiError("missing_file", "A TIFF file is required.", 400)
        extension = _tiff_extension(upload.filename)
        image_id, directory = self.store.create("images")
        filename = self.store.safe_filename(upload.filename, f"image{extension}")
        if Path(filename).suffix.lower() not in TIFF_EXTENSIONS:
            filename += extension
        path = directory / "source.tif"
        try:
            upload.save(path)
            metadata = self.create_from_existing_path(path, filename, image_id=image_id, directory=directory)
        except Exception:
            if directory.exists():
                shutil.rmtree(directory)
            raise
        return metadata

    def create_from_existing_path(self, source_path: Path, filename: str, *, image_id: str | None = None, directory: Path | None = None) -> dict:
        if directory is None:
            image_id, directory = self.store.create("images", image_id)
            shutil.copyfile(source_path, directory / "source.tif")
            source_path = directory / "source.tif"
        assert image_id is not None
        details = inspect_tiff(source_path)
        metadata = {"image_id": image_id, "filename": self.store.safe_filename(filename, "image.tif"), **details}
        self.store.write_json("images", image_id, metadata)
        return metadata

    def get(self, image_id: str) -> dict:
        return self.store.read_json("images", image_id)

    def path(self, image_id: str) -> Path:
        path = self.store.resource_dir("images", image_id) / "source.tif"
        if not path.is_file():
            raise ApiError("image_not_found", "The requested image was not found.", 404)
        return path

    def preview(self, image_id: str, channel_index: int, max_size: int = 1600, normalization: str = "percentile") -> Path:
        metadata = self.get(image_id)
        if channel_index < 0 or channel_index >= metadata["channel_count"]:
            raise ApiError("channel_not_found", "The requested channel does not exist.", 404, {"channel_index": channel_index})
        if max_size < 32 or max_size > 4096:
            raise ApiError("invalid_max_size", "max_size must be between 32 and 4096.", 400)
        if normalization not in {"percentile", "minmax"}:
            raise ApiError("invalid_normalization", "normalization must be percentile or minmax.", 400)
        cache = self.store.resource_dir("images", image_id) / "previews"
        cache.mkdir(exist_ok=True)
        target = cache / f"c{channel_index}-{max_size}-{normalization}.png"
        if target.exists():
            return target

        with rasterio.open(self.path(image_id)) as source:
            scale = min(1.0, max_size / max(source.width, source.height))
            output_width = max(1, round(source.width * scale))
            output_height = max(1, round(source.height * scale))
            band = source.read(channel_index + 1, out_shape=(output_height, output_width), resampling=Resampling.bilinear)
        finite = band[np.isfinite(band)] if np.issubdtype(band.dtype, np.floating) else band.reshape(-1)
        if finite.size == 0:
            display = np.zeros(band.shape, dtype=np.uint8)
        else:
            if normalization == "percentile":
                low, high = np.percentile(finite, [2, 98])
            else:
                low, high = finite.min(), finite.max()
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                display = np.zeros(band.shape, dtype=np.uint8)
            else:
                display = np.clip((band.astype(np.float64) - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)
        Image.fromarray(display, mode="L").save(target, format="PNG")
        return target

    def delete(self, image_id: str) -> None:
        for annotation_dir in (self.store.root / "annotations").iterdir():
            metadata_path = annotation_dir / "metadata.json"
            if metadata_path.is_file():
                try:
                    import json
                    if json.loads(metadata_path.read_text(encoding="utf-8")).get("image_id") == image_id:
                        raise ApiError("image_in_use", "The image is referenced by an active annotation.", 409)
                except ApiError:
                    raise
                except (json.JSONDecodeError, OSError):
                    continue
        self.store.delete("images", image_id)
