"""Make LightGBM importable on Linux hosts that lack the OpenMP runtime (libgomp.so.1).

Serverless Linux images such as Vercel's Python runtime (Amazon Linux 2023 / AWS Lambda) do not ship libgomp, and
LightGBM's native library links against it. When the system has none, load the copy vendored in payscore/_vendor
(taken from the Amazon Linux 2023 `libgomp` package, GCC Runtime Library Exception) with RTLD_GLOBAL, so the dynamic
linker resolves LightGBM's `libgomp.so.1` dependency to it. Elsewhere this does nothing.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import platform
import sys
from pathlib import Path

VENDORED_LIBGOMP = Path(__file__).resolve().parent / "_vendor" / "libgomp.so.1"


def ensure_openmp() -> bool:
    """Return True when the vendored libgomp was loaded."""
    if not sys.platform.startswith("linux") or platform.machine() not in {"x86_64", "AMD64"}:
        return False
    if ctypes.util.find_library("gomp"):
        return False
    try:
        ctypes.CDLL("libgomp.so.1", mode=ctypes.RTLD_GLOBAL)
        return False  # the system has it after all
    except OSError:
        pass
    if not VENDORED_LIBGOMP.exists():
        return False
    ctypes.CDLL(str(VENDORED_LIBGOMP), mode=ctypes.RTLD_GLOBAL)
    return True
