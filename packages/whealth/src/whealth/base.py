"""Base abstractions for health controls."""

from abc import ABC, abstractmethod
from typing import Any


class BaseControl(ABC):
    """Abstract base class for all health controls."""

    @abstractmethod
    def check(self) -> Any:
        """Run the control check and return the result."""
