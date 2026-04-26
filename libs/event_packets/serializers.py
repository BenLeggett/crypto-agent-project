"""Event packet serializers."""

from __future__ import annotations

import json
from typing import Any

from libs.event_packets.schemas import EventPacket, canonical_event_packet_json, event_packet_from_mapping


def event_packet_to_json(packet: EventPacket) -> str:
    """Serialize one event packet to deterministic compact JSON."""

    if not isinstance(packet, EventPacket):
        raise TypeError("packet must be an EventPacket")
    return canonical_event_packet_json(packet)


def event_packet_from_json(payload: str) -> EventPacket:
    """Parse one event packet from a JSON string."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("payload must be a non-empty JSON string")
    parsed: Any = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("event packet JSON must contain an object")
    return event_packet_from_mapping(parsed)


def event_packet_to_jsonl_line(packet: EventPacket) -> str:
    """Serialize one event packet as a JSONL line."""

    return f"{event_packet_to_json(packet)}\n"


def event_packet_from_jsonl_line(line: str) -> EventPacket:
    """Parse one event packet from a JSONL line."""

    return event_packet_from_json(line.strip())


__all__ = [
    "event_packet_from_json",
    "event_packet_from_jsonl_line",
    "event_packet_to_json",
    "event_packet_to_jsonl_line",
]
