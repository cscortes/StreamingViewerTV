"""PyInstaller entry point.

Kept separate from app.py so the frozen build has one obvious script to
point at; just delegates to the real startup logic.
"""

from __future__ import annotations

import multiprocessing

from stream_viewer.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
