from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def put(self, key: str, content: bytes) -> Path:
        relative = Path(*PurePosixPath(key).parts)
        target = (self.root / relative).resolve()
        if self.root not in target.parents:
            raise ValueError("Invalid storage key")
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)
        return target
