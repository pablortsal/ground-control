"""Abstract base class for ticket sources."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class TicketPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Ticket:
    """A work item to be processed by agents."""

    id: str
    title: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    labels: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BaseTicketSource(abc.ABC):
    """Interface for loading tickets from any source."""

    @abc.abstractmethod
    async def load_tickets(self) -> list[Ticket]:
        """Load all available tickets."""
        ...

    @abc.abstractmethod
    async def get_ticket(self, ticket_id: str) -> Ticket | None:
        """Get a single ticket by ID."""
        ...

    @abc.abstractmethod
    async def update_ticket_status(self, ticket_id: str, status: TicketStatus) -> None:
        """Update the status of a ticket."""
        ...
