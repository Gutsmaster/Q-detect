"""Q-DETECT: teleportation-based Weng 2021 QDS + basis-resolved monitor."""

__version__ = "0.1.0"

from qdetect.simulator import run_pipeline, SimulationConfig

__all__ = ["run_pipeline", "SimulationConfig", "__version__"]
