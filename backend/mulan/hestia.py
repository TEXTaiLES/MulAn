"""HTTP client for the HESTIA MulAn endpoints (``/api/v1`` on the HESTIA API).

MulAn's backend calls HESTIA on behalf of the signed-in user by forwarding the
portal's refresh-token cookie. HESTIA authenticates and authorizes every call,
so MulAn never decides on its own who may read or write a resource.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, BinaryIO

import requests

from .errors import ApiError


class HestiaClient:
    def __init__(self, api_url: str, cookie_name: str, timeout: float = 30):
        self.api_url = api_url.rstrip("/")
        self.cookie_name = cookie_name
        self.timeout = timeout

    def _request(self, method: str, path: str, token: str | None, *, stream: bool = False, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop("headers", {})
        if token:
            # An explicit header instead of a cookie jar keeps one user's
            # credentials from ever being reused for another user's call.
            headers["Cookie"] = f"{self.cookie_name}={token}"
        try:
            response = requests.request(method, f"{self.api_url}{path}", headers=headers, timeout=self.timeout, stream=stream, **kwargs)
        except requests.RequestException as exc:
            raise ApiError("hestia_unavailable", "HESTIA could not be reached.", 502) from exc
        if response.status_code >= 400:
            raise self._error(response)
        return response

    @staticmethod
    def _error(response: requests.Response) -> ApiError:
        try:
            error = response.json()["error"]
            return ApiError(error["code"], error["message"], response.status_code, error.get("details") or {})
        except (ValueError, KeyError, TypeError):
            status = response.status_code if response.status_code < 500 else 502
            return ApiError("hestia_error", f"HESTIA returned an unexpected response ({response.status_code}).", status)
        finally:
            response.close()

    def session(self, token: str | None) -> dict:
        return self._request("GET", "/api/v1/session", token).json()

    def list_images(self, token: str, params: dict[str, str]) -> dict:
        return self._request("GET", "/api/v1/multispectral/images", token, params=params).json()

    def image(self, token: str, image_id: str) -> dict:
        return self._request("GET", f"/api/v1/multispectral/images/{image_id}", token).json()

    def open_image_file(self, token: str, image_id: str) -> requests.Response:
        """Streamed source TIFF; the caller must close the response."""
        return self._request("GET", f"/api/v1/multispectral/images/{image_id}/file", token, stream=True)

    def download_image(self, token: str, image_id: str, target: Path) -> None:
        with self.open_image_file(token, image_id) as response, target.open("wb") as output:
            shutil.copyfileobj(response.raw, output, 1024 * 1024)

    def upload_image(self, token: str, source: BinaryIO, filename: str) -> dict:
        return self._request("POST", "/api/v1/multispectral/images", token, files={"file": (filename, source, "image/tiff")}).json()

    def annotation(self, token: str, image_id: str) -> dict | None:
        """The image's stored annotation, or None when it has none yet."""
        try:
            return self._request("GET", f"/api/v1/multispectral/images/{image_id}/annotation", token).json()
        except ApiError as error:
            if error.code == "annotation_not_found":
                return None
            raise

    def annotation_package(self, token: str, image_id: str) -> bytes:
        return self._request("GET", f"/api/v1/multispectral/images/{image_id}/annotation/package", token).content

    def save_annotation(self, token: str, image_id: str, package: bytes, *, overwrite: bool, expected_revision: int | None) -> dict:
        form = {"overwrite": "true" if overwrite else "false"}
        if expected_revision is not None:
            form["expected_revision"] = str(expected_revision)
        files = {"package": ("annotation.zip", package, "application/zip")}
        return self._request("PUT", f"/api/v1/multispectral/images/{image_id}/annotation", token, data=form, files=files).json()
