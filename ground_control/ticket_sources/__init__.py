"""Ticket source abstractions and implementations."""

from ground_control.ticket_sources.base import BaseTicketSource, Ticket
from ground_control.ticket_sources.local_yaml import LocalYAMLTicketSource

SOURCES: dict[str, type[BaseTicketSource]] = {
    "local_yaml": LocalYAMLTicketSource,
}


def get_ticket_source(name: str, **kwargs) -> BaseTicketSource:
    """Get a ticket source by name."""
    if name not in SOURCES:
        raise ValueError(
            f"Unknown ticket source: {name}. Available: {list(SOURCES.keys())}"
        )
    return SOURCES[name](**kwargs)

__all__ = [
    "BaseTicketSource",
    "Ticket",
    "LocalYAMLTicketSource",
    "get_ticket_source",
    "SOURCES",
]
