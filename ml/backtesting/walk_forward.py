"""Walk-forward validation scaffold (MVP-6)."""

from __future__ import annotations

from typing import Any, Iterator


def walk_forward_splits(*args: Any, **kwargs: Any) -> Iterator[tuple[Any, Any, Any]]:
    raise NotImplementedError("walk_forward_splits lands in MVP-6")
    yield  # pragma: no cover
