from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from ..errors import ApiError


@dataclass
class ConversionResult:
    path: Path
    width: int
    height: int
    count: int
    dtype: str
    channel_names: list[str | None]


def parse_channel_names(raw: str | None, count: int) -> list[str | None]:
    if raw in (None, ""):
        return [None] * count
    try:
        names = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("invalid_channel_names", "channel_names must be a JSON array.", 400) from exc
    if not isinstance(names, list) or len(names) != count or any(name is not None and not isinstance(name, str) for name in names):
        raise ApiError("channel_name_count_mismatch", "channel_names must contain exactly one string or null per input band.", 422, {"expected": count})
    return names


def parse_manifest(raw: str | None, files: list[FileStorage]) -> list[str | None] | None:
    if not raw:
        return None
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("invalid_manifest", "manifest must be valid JSON.", 400) from exc
    if not isinstance(manifest, dict) or set(manifest) != {"bands"} or not isinstance(manifest["bands"], list):
        raise ApiError("invalid_manifest", "manifest must contain only a bands array.", 422)
    bands = manifest["bands"]
    if len(bands) != len(files):
        raise ApiError("invalid_manifest", "manifest must describe every input file exactly once.", 422)
    names: list[str | None] = [None] * len(files)
    indexes = set()
    for band in bands:
        if not isinstance(band, dict) or set(band) - {"file_index", "name"} or not isinstance(band.get("file_index"), int):
            raise ApiError("invalid_manifest", "Each manifest band needs an integer file_index and optional name.", 422)
        index = band["file_index"]
        name = band.get("name")
        if index < 0 or index >= len(files) or index in indexes or (name is not None and not isinstance(name, str)):
            raise ApiError("invalid_manifest", "Manifest file indexes must be unique and in range.", 422)
        indexes.add(index)
        names[index] = name
    return names


def _read_bmp(upload: FileStorage) -> np.ndarray:
    filename = upload.filename or ""
    if Path(filename).suffix.lower() != ".bmp":
        raise ApiError("unsupported_media_type", "Every input file must have a .bmp extension.", 415, {"filename": filename})
    try:
        upload.stream.seek(0)
        with Image.open(upload.stream) as image:
            if image.format != "BMP":
                raise ApiError("invalid_bmp", "The input file is not a valid BMP.", 422, {"filename": filename})
            image.load()
            if image.mode == "P":
                palette = image.getpalette()
                indexes = np.asarray(image)
                used = np.unique(indexes)
                if palette is None or any(palette[int(value) * 3] != palette[int(value) * 3 + 1] or palette[int(value) * 3] != palette[int(value) * 3 + 2] for value in used):
                    raise ApiError("color_bmp_not_supported", "Color BMP images cannot be used as single-band inputs.", 422, {"filename": filename})
                array = np.asarray(image.convert("L"))
            elif image.mode == "1":
                array = np.asarray(image, dtype=np.uint8) * 255
            else:
                array = np.asarray(image)
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError("invalid_bmp", "The input file is not a readable BMP.", 422, {"filename": filename}) from exc
    if array.ndim == 3:
        if array.shape[2] != 3 or not (np.array_equal(array[..., 0], array[..., 1]) and np.array_equal(array[..., 0], array[..., 2])):
            raise ApiError("color_bmp_not_supported", "Color BMP images cannot be used as single-band inputs.", 422, {"filename": filename})
        array = array[..., 0]
    if array.ndim != 2 or not np.issubdtype(array.dtype, np.integer):
        raise ApiError("unsupported_bmp", "The BMP must decode to one integer grayscale raster.", 422, {"filename": filename})
    return np.array(array, copy=True)


def convert_bmps(files: list[FileStorage], output_path: Path, channel_names: list[str | None]) -> ConversionResult:
    if not files:
        raise ApiError("missing_files", "At least one BMP file is required.", 400)
    arrays = [_read_bmp(upload) for upload in files]
    expected_shape = arrays[0].shape
    expected_dtype = arrays[0].dtype
    for index, array in enumerate(arrays[1:], start=1):
        if array.shape != expected_shape:
            raise ApiError("dimension_mismatch", "All BMP images must have identical dimensions.", 422, {
                "file": files[index].filename,
                "expected": [expected_shape[1], expected_shape[0]],
                "received": [array.shape[1], array.shape[0]],
            })
        if array.dtype != expected_dtype:
            raise ApiError("datatype_mismatch", "All BMP images must have compatible datatypes.", 422, {"file": files[index].filename})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", driver="GTiff", width=expected_shape[1], height=expected_shape[0], count=len(arrays), dtype=expected_dtype) as target:
        for index, (array, name) in enumerate(zip(arrays, channel_names, strict=True), start=1):
            target.write(array, index)
            if name:
                target.set_band_description(index, name)
    return ConversionResult(output_path, expected_shape[1], expected_shape[0], len(arrays), str(expected_dtype), channel_names)


def temporary_output() -> tuple[tempfile.TemporaryDirectory, Path]:
    directory = tempfile.TemporaryDirectory(prefix="mulan-convert-")
    return directory, Path(directory.name) / "output.tif"
