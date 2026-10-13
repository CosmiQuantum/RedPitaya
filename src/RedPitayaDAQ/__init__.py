"""Red Pitaya acquisition interfaces. [AI generated]

Import the device driver from its module on a Red Pitaya with ``rp`` installed.
The package root exposes the remote interface and data analysis functions without
importing device bindings. Data analysis requires the external recon_algorithms
module.
"""

from .RedPitayaRemoteInterface import RedPitayaRemoteInterface
from .RedPitayaDataHandler import (
    loadData,
    plotData,
    applyMatchFilter,
    get_multijumps,
    graph_multijumps,
)

__all__ = [
    "RedPitayaRemoteInterface",
    "loadData",
    "plotData",
    "applyMatchFilter",
    "get_multijumps",
    "graph_multijumps",
]
