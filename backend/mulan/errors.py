from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def as_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}

