"""Local YAML file ticket source."""

from __future__ import annotations

from pathlib import Path

import yaml

from ground_control.ticket_sources.base import (
    BaseTicketSource,
    Ticket,
    TicketPriority,
    TicketStatus,
)


class LocalYAMLTicketSource(BaseTicketSource):
    """Loads tickets from YAML files in a local directory.

    Supports two layouts:
    - A single tickets.yaml with a list of tickets
    - One .yaml file per ticket in the directory
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    async def load_tickets(self) -> list[Ticket]:
        if not self.path.exists():
            return []

        tickets: list[Ticket] = []

        single_file = self.path / "tickets.yaml"
        if single_file.exists():
            tickets.extend(self._load_from_file(single_file))

        for yaml_file in sorted(self.path.glob("*.yaml")):
            if yaml_file.name == "tickets.yaml":
                continue
            tickets.extend(self._load_from_file(yaml_file))

        for yml_file in sorted(self.path.glob("*.yml")):
            tickets.extend(self._load_from_file(yml_file))

        seen_ids: set[str] = set()
        unique: list[Ticket] = []
        for t in tickets:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                unique.append(t)
        return unique

    async def get_ticket(self, ticket_id: str) -> Ticket | None:
        tickets = await self.load_tickets()
        for t in tickets:
            if t.id == ticket_id:
                return t
        return None

    async def update_ticket_status(self, ticket_id: str, status: TicketStatus) -> None:
        """Update status in the YAML file.

        Scans all files to find the ticket and rewrites the file with the new status.
        """
        for yaml_file in self._all_yaml_files():
            if self._update_in_file(yaml_file, ticket_id, status):
                return
        raise KeyError(f"Ticket '{ticket_id}' not found in any YAML file.")

    def _all_yaml_files(self) -> list[Path]:
        if not self.path.exists():
            return []
        files = list(self.path.glob("*.yaml")) + list(self.path.glob("*.yml"))
        return sorted(files)

    def _load_from_file(self, path: Path) -> list[Ticket]:
        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            return []

        if isinstance(data, list):
            return [self._parse_ticket(item) for item in data]

        if isinstance(data, dict):
            if "tickets" in data:
                return [self._parse_ticket(item) for item in data["tickets"]]
            return [self._parse_ticket(data)]

        return []

    def _parse_ticket(self, data: dict) -> Ticket:
        return Ticket(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            priority=TicketPriority(data.get("priority", "medium")),
            status=TicketStatus(data.get("status", "open")),
            labels=data.get("labels", []),
            dependencies=data.get("dependencies", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            metadata=data.get("metadata", {}),
        )

    def _update_in_file(self, path: Path, ticket_id: str, status: TicketStatus) -> bool:
        with open(path) as f:
            data = yaml.safe_load(f)

        if data is None:
            return False

        items: list[dict] | None = None
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "tickets" in data:
            items = data["tickets"]
        elif isinstance(data, dict) and str(data.get("id", "")) == ticket_id:
            data["status"] = status.value
            with open(path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            return True

        if items:
            for item in items:
                if str(item.get("id", "")) == ticket_id:
                    item["status"] = status.value
                    with open(path, "w") as f:
                        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
                    return True

        return False
