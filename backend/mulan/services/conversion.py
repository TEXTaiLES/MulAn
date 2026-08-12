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


@dataclass
class BmpInput:
    filename: str
    bands: np.ndarray

    @property
    def count(self) -> int:
        return self.bands.shape[0]

    @property
    def shape(self) -> tuple[int, int]:
        return self.bands.shape[1], self.bands.shape[2]


def parse_channel_names(raw: str | None, count: int) -> list[str | None]:
    if raw in (None, ""):
        return [None] * count
    try:
        names = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("invalid_channel_names", "channel_names must be a JSON array.", 400) from exc
    if not isinstance(names, list) or len(names) != count or any(name is not None and not isinstance(name, str) for name in names):
        raise ApiError("channel_name_count_mismatch", "channel_names must contain exactly one string or null per output band.", 422, {"expected": count})
    return names


def parse_manifest(raw: str | None, files: list[FileStorage], channel_counts: list[int] | None = None) -> list[str | None] | None:
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
    if channel_counts is None:
        return names
    expanded: list[str | None] = []
    for name, count in zip(names, channel_counts, strict=True):
        if count == 1:
            expanded.append(name)
        elif count == 3:
            expanded.extend([f"{name}:{component}" if name else None for component in "RGB"])
        else:  # Only one- and three-band BMP inputs are prepared by this service.
            raise ApiError("unsupported_bmp", "The BMP layout is not supported.", 422)
    return expanded


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
                    raise ApiError("color_bmp_not_supported", "Color-paletted BMP images are not supported; use an RGB BMP.", 422, {"filename": filename})
                array = np.asarray(image.convert("L"))
            elif image.mode == "1":
                array = np.asarray(image, dtype=np.uint8) * 255
            elif image.mode == "RGB":
                array = np.moveaxis(np.asarray(image), 2, 0)
            else:
                array = np.asarray(image)
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError("invalid_bmp", "The input file is not a readable BMP.", 422, {"filename": filename}) from exc
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    if array.ndim != 3 or array.shape[0] not in {1, 3} or not np.issubdtype(array.dtype, np.integer):
        raise ApiError("unsupported_bmp", "The BMP must decode to an integer grayscale or RGB raster.", 422, {"filename": filename})
    return np.array(array, copy=True)


def prepare_bmps(files: list[FileStorage]) -> list[BmpInput]:
    if not files:
        raise ApiError("missing_files", "At least one BMP file is required.", 400)
    inputs = [BmpInput(upload.filename or "", _read_bmp(upload)) for upload in files]
    expected_shape = inputs[0].shape
    expected_dtype = inputs[0].bands.dtype
    for input_bmp in inputs[1:]:
        if input_bmp.shape != expected_shape:
            raise ApiError("dimension_mismatch", "All BMP images must have identical dimensions.", 422, {
                "file": input_bmp.filename,
                "expected": [expected_shape[1], expected_shape[0]],
                "received": [input_bmp.shape[1], input_bmp.shape[0]],
            })
        if input_bmp.bands.dtype != expected_dtype:
            raise ApiError("datatype_mismatch", "All BMP images must have compatible datatypes.", 422, {"file": input_bmp.filename})
    return inputs


def convert_bmps(inputs: list[BmpInput], output_path: Path, channel_names: list[str | None]) -> ConversionResult:
    if not inputs:
        raise ApiError("missing_files", "At least one BMP file is required.", 400)
    output_count = sum(input_bmp.count for input_bmp in inputs)
    if len(channel_names) != output_count:
        raise ApiError("channel_name_count_mismatch", "channel_names must contain exactly one string or null per output band.", 422, {"expected": output_count})
    expected_shape = inputs[0].shape
    expected_dtype = inputs[0].bands.dtype
    descriptions: list[str | None] = []
    for input_bmp in inputs:
        stem = Path(input_bmp.filename).stem
        defaults = [None] if input_bmp.count == 1 else [f"{stem}:{component}" for component in "RGB"]
        offset = len(descriptions)
        descriptions.extend(channel_names[offset + index] or default for index, default in enumerate(defaults))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", driver="GTiff", width=expected_shape[1], height=expected_shape[0], count=output_count, dtype=expected_dtype) as target:
        output_index = 1
        for input_bmp in inputs:
            for array in input_bmp.bands:
                target.write(array, output_index)
                description = descriptions[output_index - 1]
                if description:
                    target.set_band_description(output_index, description)
                output_index += 1
    return ConversionResult(output_path, expected_shape[1], expected_shape[0], output_count, str(expected_dtype), descriptions)


def temporary_output() -> tuple[tempfile.TemporaryDirectory, Path]:
    directory = tempfile.TemporaryDirectory(prefix="mulan-convert-")
    return directory, Path(directory.name) / "output.tif"
