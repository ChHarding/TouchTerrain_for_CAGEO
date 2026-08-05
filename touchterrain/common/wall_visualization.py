from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from touchterrain.common.BorderEdge import BorderEdge

BorderEdgePlotSource: TypeAlias = Literal[
    "stored_clipped_edge",
    "contained_cardinal_wall",
]


@dataclass(frozen=True)
class BorderEdgePlotRecord:
    """A border edge plus debug-only wall visualization metadata."""

    edge: BorderEdge
    source: BorderEdgePlotSource = "stored_clipped_edge"
