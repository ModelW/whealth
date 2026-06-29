"""Base abstractions for health controls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable


type Outcome = Literal[
    "warning",
    "error",
    "internal_error",
]
"""Result of a single control check.

Controls only return non-OK outcomes because there is no need to
store or transmit a positive result — the absence of a Failure
already means success.

Values
------
warning
    The control is in a degraded but still-operational state.
    Dependent checks should still run.
error
    The check has failed and dependent checks cannot rely on it.
internal_error
    The check itself is broken (e.g. an unhandled exception in the
    control code).
"""


@dataclass(frozen=True)
class RestartRemediation:
    """Restart a specific component to fix the issue."""

    components: list[str]


@dataclass(frozen=True)
class PyRemediation:
    """Call a Python function to try and fix the issue."""

    func: Callable[[], None]


@dataclass(frozen=True)
class SuggestionRemediation:
    """Suggest a manual action to the admin to fix the issue."""

    message: str


type Remediation = RestartRemediation | PyRemediation | SuggestionRemediation


@dataclass(frozen=True)
class Failure:
    """A single failure or warning produced by a control check.

    This dataclass must remain trivially serializable so instances can be
    stored in and reconstructed from the database.  No subclassing or
    additional state is allowed beyond the defined fields.
    """

    key: str
    outcome: Outcome
    context: Any = None


class BaseControl(ABC):
    """Abstract base class for all health controls."""

    @abstractmethod
    def get_failures(self) -> list[Failure]:
        """Run the control check and return zero or more failures.

        If you are going to be returning potentially many failures, make sure to
        cap the number of potential items that you can return:

        - Limit to 100 items or so (if you need to be dealing with more items
          manually you probably need to find the root cause of the issue before
          moving forward)
        - Make sure that the order of failures is stable so that the output of
          this function is usefully comparable across runs.
        """

    def get_remediation(self, failure: Failure) -> Remediation | None:
        """Return a remediation for this failure, or None."""
        return None
