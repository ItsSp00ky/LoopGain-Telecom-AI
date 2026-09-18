"""Register the conda environment's DLL directory on Windows.

WHY THIS FILE EXISTS. Running `python.exe` from a conda environment *directly*
-- `D:\\Anaconda\\envs\\cvm\\python.exe script.py` -- is not the same as running
it after `conda activate cvm`. Activation prepends the environment's
`Library\\bin` to PATH; a direct invocation does not. Everything pure-Python
works identically either way, so the difference is invisible until something
loads a native library.

Then it fails like this:

    OSError: [WinError -1066598273] Windows Error 0xc06d007f

raised from inside `threadpoolctl`, after `scipy.linalg` has loaded MKL and
something asks how many threads it is using. 0xc06d007f is a delay-load DLL
failure, so the message names neither the DLL nor the caller. The same missing
path also breaks `import torch` with a `shm.dll` error in some orders, which
takes CTGAN down with it.

It reads like an OpenMP conflict and it is not one: `KMP_DUPLICATE_LIB_OK=TRUE`
and `OMP_NUM_THREADS=1` both leave it failing, and adding `Library\\bin` to the
search path fixes it outright.

`os.add_dll_directory` is the supported way to say this from inside Python
(3.8+), so a direct invocation, a CI runner and an IDE that does not activate
the environment all behave like an activated shell.

No-ops on anything that is not Windows, and on an already-activated shell.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

# Kept so a caller can report what was registered, and so a test can assert
# the registration happened rather than trusting it.
REGISTERED: list[str] = []


def register_conda_dll_directories() -> list[str]:
    """Add this interpreter's native library directories to the DLL path.

    Returns the directories registered, in order. Safe to call more than once:
    Windows tolerates a duplicate registration and the list is de-duplicated.
    """
    if sys.platform != "win32":
        return []

    prefix = Path(sys.prefix)

    # ORDER MATTERS, and getting it wrong swaps one failure for another.
    #
    # torch ships its own MKL and OpenMP in `site-packages/torch/lib`. Conda
    # ships different versions in `Library/bin`. Whichever appears first on
    # PATH wins for everything loaded afterwards:
    #
    #   Library/bin absent          -> threadpoolctl cannot query MKL,
    #                                  OSError 0xc06d007f
    #   Library/bin first           -> torch loads conda's MKL instead of its
    #                                  own and dies on shm.dll, WinError 127
    #   torch/lib then Library/bin   -> both work
    #
    # So torch's directory goes first. It is found by inspecting the installed
    # package path rather than by importing torch, because importing it is the
    # thing that fails.
    site_packages = prefix / "Lib" / "site-packages"
    candidates = [
        site_packages / "torch" / "lib",
        prefix / "Library" / "bin",
        prefix / "Library" / "mingw-w64" / "bin",
        prefix / "Library" / "usr" / "bin",
        prefix / "DLLs",
    ]

    added: list[str] = []
    for directory in candidates:
        if not directory.is_dir() or str(directory) in REGISTERED:
            continue

        # BOTH mechanisms, and both are needed.
        #
        # `os.add_dll_directory` is the documented modern way and it is not
        # sufficient on its own here: it governs how Python resolves a DLL it
        # loads directly, but MKL's own transitive dependencies are resolved by
        # the Windows loader using PATH. Registering the directory and leaving
        # PATH alone still fails with the same 0xc06d007f.
        #
        # Prepending to PATH is what actually fixes it. The add_dll_directory
        # call is kept because it is the correct declaration of intent and it
        # covers loaders that do honour it. A directory that cannot be
        # registered is not worth failing an import over.
        with contextlib.suppress(OSError):
            os.add_dll_directory(str(directory))

        path = os.environ.get("PATH", "")
        if str(directory).lower() not in path.lower():
            os.environ["PATH"] = f"{directory}{os.pathsep}{path}"

        REGISTERED.append(str(directory))
        added.append(str(directory))

    _preload_torch()
    return added


def _preload_torch() -> bool:
    """Import torch now, before anything can call `threadpoolctl.threadpool_info`.

    THE SECOND HALF OF THE FIX, and the non-obvious one. With `Library/bin` on
    PATH, MKL resolves and `threadpool_info()` works -- but calling it leaves
    the OpenMP runtimes in a state where `import torch` then fails with
    `WinError 127` on `shm.dll`. Since sklearn calls `threadpool_limits`
    internally, and CTGAN goes through sklearn, any import order that touches
    sklearn before torch is a live grenade.

    Measured, with `Library/bin` on PATH throughout:

        scipy -> threadpool_info() -> torch      torch CRASHES
        torch -> scipy -> threadpool_info()      both fine

    So torch is imported here, at package import, where it is guaranteed to be
    first. It is a hard dependency of SDV's CTGAN and TVAE, so this costs
    nothing that was optional; where it genuinely is absent the failure is
    swallowed and the copula path still works.
    """
    try:
        import torch  # noqa: F401
    except (ImportError, OSError):
        return False
    return True
