"""Registries: `@handler("gps.where")` for read intents, `@action("wo.create")` for confirmed writes. Handler modules are imported by `handlers/__init__.py`."""
from __future__ import annotations

from app.services.assistant.types import ActionExecutor, Handler

HANDLERS: dict[str, Handler] = {}
ACTIONS: dict[str, ActionExecutor] = {}


def handler(intent_id: str):
    def wrap(fn: Handler) -> Handler:
        HANDLERS[intent_id] = fn
        return fn

    return wrap


def action(kind: str):
    def wrap(fn: ActionExecutor) -> ActionExecutor:
        ACTIONS[kind] = fn
        return fn

    return wrap
