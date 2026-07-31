"""Chaquopy entrypoint: set Android env, then run the FastAPI viewer.

Must not import stream_viewer.app until STREAM_VIEWER_ANDROID is set, because
export/static paths are resolved at module import time.
"""

from __future__ import annotations

import os


def start(host: str = "127.0.0.1", port: int = 8787) -> None:
    os.environ["STREAM_VIEWER_ANDROID"] = "1"
    os.environ["STREAM_VIEWER_NO_BROWSER"] = "1"
    # Chaquopy already sets HOME to the app files directory.
    from stream_viewer.app import run_server

    run_server(host=host, port=int(port))
