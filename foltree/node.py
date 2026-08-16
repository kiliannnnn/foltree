"""The tree model shared by every scanner, renderer and parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional


@dataclass
class Node:
    """A single file or directory in a structure tree.

    `size` is the byte size for files and the summed size of descendants for
    directories. It stays None when sizes were not collected (parsed text
    usually has no size information).
    """

    name: str
    is_dir: bool = False
    children: List["Node"] = field(default_factory=list)
    size: Optional[int] = None
    truncated: bool = False
    error: Optional[str] = None

    def add(self, child: "Node") -> "Node":
        self.children.append(child)
        return child

    def walk(self) -> Iterator["Node"]:
        """Depth-first iteration including self."""
        yield self
        for child in self.children:
            yield from child.walk()

    def sort(self) -> None:
        """Sort in place: directories first, then files, each case-insensitive."""
        self.children.sort(key=lambda n: (not n.is_dir, n.name.lower(), n.name))
        for child in self.children:
            child.sort()

    @property
    def file_count(self) -> int:
        return sum(1 for n in self.walk() if not n.is_dir)

    @property
    def dir_count(self) -> int:
        # -1 so a directory does not count itself.
        return sum(1 for n in self.walk() if n.is_dir) - (1 if self.is_dir else 0)

    @property
    def total_size(self) -> int:
        return sum(n.size or 0 for n in self.walk() if not n.is_dir)

    def to_dict(self) -> dict:
        data: dict = {"name": self.name, "type": "dir" if self.is_dir else "file"}
        if self.size is not None:
            data["size"] = self.size
        if self.truncated:
            data["truncated"] = True
        if self.error:
            data["error"] = self.error
        if self.is_dir:
            data["children"] = [c.to_dict() for c in self.children]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        node = cls(
            name=data["name"],
            is_dir=data.get("type", "file") == "dir",
            size=data.get("size"),
            truncated=bool(data.get("truncated")),
            error=data.get("error"),
        )
        for child in data.get("children", []) or []:
            node.add(cls.from_dict(child))
        return node

    def __eq__(self, other: object) -> bool:
        """Structural equality, ignoring size/error bookkeeping.

        Used by the round-trip tests: what matters is that names, types and
        nesting survive a render/parse cycle.
        """
        if not isinstance(other, Node):
            return NotImplemented
        return (
            self.name == other.name
            and self.is_dir == other.is_dir
            and self.children == other.children
        )
