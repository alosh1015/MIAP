"""Compatibility surface for the engine package.

New code imports from :mod:`app.modules.inference.engines`; this module keeps the
historical import path working for the worker, heatmap service and health check.
"""

from __future__ import annotations

from app.modules.inference.engines import (  # noqa: F401
    BaseEngine,
    Prediction,
    engine_lock,
    get_engine,
    normalise_cam,
)
from app.modules.inference.engines.stub import StubEngine
from app.modules.inference.engines.xrv_chest import XrvChestEngine as TorchXRayVisionEngine

__all__ = [
    "BaseEngine",
    "Prediction",
    "StubEngine",
    "TorchXRayVisionEngine",
    "engine_lock",
    "get_engine",
    "normalise_cam",
]
