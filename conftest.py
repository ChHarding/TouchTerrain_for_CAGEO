"""Pytest configuration shared by the TouchTerrain test suite."""

import os
from pathlib import Path
import sys

import pytest


SHOW_WALL_PLOTS_ENV = "TOUCHTERRAIN_SHOW_WALL_PLOTS"
_DLL_DIRECTORY_HANDLES = []


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add opt-in controls for interactive development visualizations."""
    parser.addoption(
        "--show-wall-plots",
        action="store_true",
        default=False,
        help="Show interactive polygon-clipping wall graphs during tests.",
    )


def _configure_windows_conda_dll_search_path() -> None:
    """Expose native Conda libraries before tests import binary packages."""
    if sys.platform != "win32":
        return

    library_bin = Path(sys.prefix) / "Library" / "bin"
    if not library_bin.is_dir():
        return

    library_bin_text = str(library_bin)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if library_bin_text.casefold() not in {
        entry.casefold() for entry in path_entries if entry
    }:
        os.environ["PATH"] = os.pathsep.join(
            [library_bin_text, *path_entries]
        )

    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(
            os.add_dll_directory(library_bin_text)
        )


def pytest_configure(config: pytest.Config) -> None:
    """Select a deterministic backend before test modules import Matplotlib."""
    _configure_windows_conda_dll_search_path()

    show_wall_plots = config.getoption("--show-wall-plots")
    os.environ[SHOW_WALL_PLOTS_ENV] = "1" if show_wall_plots else "0"

    if not show_wall_plots:
        os.environ["MPLBACKEND"] = "Agg"
    else:
        os.environ["MPLBACKEND"] = "TkAgg"
