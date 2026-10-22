"""Development server: ``python -m mulan``.

Settings come from the environment or the repository-root ``.env`` file.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from . import create_app


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("MULAN_PORT", "5001"))
    create_app().run(host="127.0.0.1", port=port, debug=True)


if __name__ == "__main__":
    main()
