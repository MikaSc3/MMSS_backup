"""Resolve Conda native libraries when Windows Python is launched directly."""

import os
from pathlib import Path
import sys

_dll_handle = None


def prepare_conda_libraries():
    """Configure this process only; keep the DLL-directory handle alive."""
    global _dll_handle
    if os.name != "nt" or _dll_handle is not None:
        return
    prefix = Path(sys.prefix)
    directory = prefix / "Library" / "bin"
    if not (prefix / "conda-meta").is_dir() or not directory.is_dir():
        return
    _dll_handle = os.add_dll_directory(str(directory))
    # BLAS backends can load their dependencies through the process PATH too.
    os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
