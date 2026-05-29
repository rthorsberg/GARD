"""Upgrade-path graph cache + shortest-path traversal (F2, research.md D4).

A per-platform-family ``networkx.DiGraph`` cache holds the edge set loaded
from ``firmware_upgrade_paths``. The loader invalidates the cache after
each successful reload; queries build the graph lazily on first use.

Query semantics (FR-016..FR-019):

- ``from == to`` → zero-hop chain ``[from]`` with weight 0, no reasons.
- ``platform_family`` not in the catalog → ``ChainResult.platform_not_found``.
- Path exists → shortest-weight chain, ``hops = len(chain) - 1``,
  ``total_weight`` = sum of edge weights.
- No path between two versions in the same family → empty chain, weight
  ``None``, ``reasons[0].kind = "no_path"`` (HTTP 200, never 404).
- Cycles in the catalog → tolerated; ``networkx.shortest_path`` handles
  them; cyclic catalogs are loadable per FR-019.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import networkx as nx

__all__ = [
    "ChainResult",
    "EdgeSpec",
    "UpgradePathGraphCache",
]


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    """A single edge fed into the graph cache."""

    from_version: str
    to_version: str
    weight: int = 1


ReasonKind = Literal["no_path", "platform_not_found", "zero_hop"]


@dataclass(frozen=True, slots=True)
class ChainResult:
    chain: tuple[str, ...]
    total_weight: int | None
    hops: int
    reasons: tuple[dict[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def empty(cls, reason: ReasonKind, detail: str | None = None) -> ChainResult:
        r: dict[str, str] = {"kind": reason}
        if detail is not None:
            r["detail"] = detail
        return cls(chain=(), total_weight=None, hops=0, reasons=(r,))

    @classmethod
    def zero_hop(cls, version: str) -> ChainResult:
        return cls(chain=(version,), total_weight=0, hops=0, reasons=())


class UpgradePathGraphCache:
    """Per-process cache of ``networkx.DiGraph`` keyed by ``platform_family``.

    Construction is lazy: the first query for a family builds the graph
    from the supplied edge iterable. The loader calls :meth:`invalidate`
    (or :meth:`rebuild`) after each reload pass so subsequent queries see
    the new state.
    """

    def __init__(self) -> None:
        self._graphs: dict[str, nx.DiGraph] = {}

    def invalidate(self, platform_family: str | None = None) -> None:
        """Drop the cached graph for ``platform_family`` (or all)."""
        if platform_family is None:
            self._graphs.clear()
        else:
            self._graphs.pop(platform_family, None)

    def rebuild(
        self, platform_family: str, edges: Iterable[EdgeSpec]
    ) -> nx.DiGraph:
        """Replace the cached graph for ``platform_family``."""
        g = nx.DiGraph()
        for e in edges:
            g.add_edge(e.from_version, e.to_version, weight=e.weight)
        self._graphs[platform_family] = g
        return g

    def has_platform(self, platform_family: str) -> bool:
        return platform_family in self._graphs

    def shortest_path(
        self,
        platform_family: str,
        from_version: str,
        to_version: str,
    ) -> ChainResult:
        """Compute the shortest-weight chain or return a reasoned empty result.

        Pure: does not consult the database directly. The caller (typically
        the firmware_upgrade_paths router) primes the cache via
        :meth:`rebuild` before calling this — or hands the edge iterator
        through :meth:`with_edges` for one-shot queries.
        """
        if from_version == to_version:
            return ChainResult.zero_hop(from_version)

        g = self._graphs.get(platform_family)
        if g is None:
            return ChainResult.empty(
                "platform_not_found",
                f"no edges loaded for platform_family={platform_family}",
            )
        if from_version not in g.nodes or to_version not in g.nodes:
            return ChainResult.empty(
                "no_path",
                f"version not in graph: from={from_version!r} to={to_version!r}",
            )

        try:
            path: Sequence[str] = nx.shortest_path(
                g, source=from_version, target=to_version, weight="weight"
            )
        except nx.NetworkXNoPath:
            return ChainResult.empty("no_path")

        total = 0
        for u, v in itertools.pairwise(path):
            total += int(g.edges[u, v].get("weight", 1))

        return ChainResult(
            chain=tuple(path),
            total_weight=total,
            hops=len(path) - 1,
        )

    def with_edges(
        self,
        platform_family: str,
        edges: Iterable[EdgeSpec],
        from_version: str,
        to_version: str,
    ) -> ChainResult:
        """One-shot helper: rebuild the platform's graph then query.

        Useful for ad-hoc queries from tests or the controller when the
        cache hasn't been primed by a loader pass yet.
        """
        self.rebuild(platform_family, edges)
        return self.shortest_path(platform_family, from_version, to_version)
