"""isotope-agents — a pluggable Python agent framework.

Configure it as a coding agent, personal assistant, or anything in between.
"""

from isotope_agents.agent import IsotopeAgent
from isotope_agents.presets import (
    ASSISTANT_PRESET,
    CODING_PRESET,
    MINIMAL_PRESET,
    PRESETS,
    Preset,
)

__all__ = [
    "IsotopeAgent",
    "Preset",
    "PRESETS",
    "CODING_PRESET",
    "ASSISTANT_PRESET",
    "MINIMAL_PRESET",
]

__version__ = "0.1.0"
