#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
"""Pure-Python implementation of the ``nest`` API used by Cicero.

The Postman RPC extension embeds FAIR's small C++ nest header for native tensor
serialization. Python application code uses this module instead of maintaining
a second pybind11 extension for the same tree operations.

Cicero only uses a tiny slice of the ``nest`` API:

    nest.flatten(n)             # 1 call site
    nest.map(f, n)              # ~23 call sites
    nest.map_many(f, *nests)    # ~4 call sites
    nest.pack_as(n, flat)       # (completeness; matches upstream)

All of these are pure tree traversals that are trivially expressible in Python.
This module reimplements them with semantics matching the upstream C++ library
and its test suite (``nest/nest_test.py``):

* Nests are nested tuples / lists / dicts. Dict children are visited in **sorted
  key order** (the C++ nests are ``std::map`` ordered by key), so ``flatten`` and
  the structural index used by ``map`` / ``map_many`` are deterministic.
* ``map(f, n)`` applies ``f`` to each leaf and returns a nest with the same
  structure (containers rebuilt as the same Python type).
* ``map_many(f, *nests)`` zips N identically-structured nests and, at each leaf,
  calls ``f`` with a **tuple** of the corresponding leaves
  (``map_many(g, (1,2), (3,4))`` with ``g=lambda x:(x[1],x[0])`` -> ``((3,1),(4,2))``).
* Any non-(tuple/list/dict) value is a leaf (tensors, scalars, None, namedtuples,
  ... — note: namedtuples are treated as leaves, matching the C++ behavior of
  only recursing into plain tuple/list/dict).
"""

from collections.abc import Callable, Iterator
from typing import Any


def _is_mapping(n: Any) -> bool:
    return isinstance(n, dict)


def _is_sequence(n: Any) -> bool:
    # Plain tuple/list only. Namedtuples are tuples but the upstream library
    # recurses into them as tuples too (they expose tuple iteration), so this is
    # consistent for the structures Cicero passes (plain dicts/lists/tuples).
    return isinstance(n, (tuple, list))


def flatten(n: Any) -> Iterator[Any]:
    """Yield the leaves of ``n`` in deterministic (sorted-key) order."""
    if _is_sequence(n):
        for sn in n:
            yield from flatten(sn)
    elif _is_mapping(n):
        for key in sorted(n.keys()):  # C++ nests are std::maps ordered by key.
            yield from flatten(n[key])
    else:
        yield n


def map(f: Callable[[Any], Any], n: Any) -> Any:
    """Apply ``f`` to each leaf of ``n``, preserving structure."""
    if _is_sequence(n):
        return type(n)(map(f, sn) for sn in n)
    elif _is_mapping(n):
        return type(n)((key, map(f, n[key])) for key in n)
    else:
        return f(n)


def _map_many(f: Callable[[Any], Any], nests):
    head = nests[0]
    if _is_sequence(head):
        return type(head)(_map_many(f, [n[i] for n in nests]) for i in range(len(head)))
    elif _is_mapping(head):
        return type(head)((key, _map_many(f, [n[key] for n in nests])) for key in head)
    else:
        # Leaf: hand f the tuple of corresponding leaves.
        return f(tuple(nests))


def map_many(f: Callable[[Any], Any], *nests: Any) -> Any:
    """Zip identically-structured nests; call ``f`` with a tuple of leaves.

    Matches upstream: ``map_many(g, (1, 2), (3, 4))`` with
    ``g = lambda x: (x[1], x[0])`` returns ``((3, 1), (4, 2))``.
    """
    if not nests:
        raise ValueError("Expected at least one nest.")
    return _map_many(f, list(nests))


def map2(f: Callable[[Any, Any], Any], n1: Any, n2: Any) -> Any:
    """Two-nest variant; ``f`` receives the two leaves as separate args."""
    return map_many(lambda x: f(x[0], x[1]), n1, n2)


def map_many2(f: Callable[[Any], Any], n1: Any, n2: Any) -> Any:
    """Alias matching the upstream ``map_many2`` name (two-nest ``map_many``)."""
    return map_many(f, n1, n2)


def pack_as(n: Any, flat) -> Any:
    """Rebuild a nest with the structure of ``n`` from a flat iterable of leaves."""
    it = iter(flat)

    def _build(sub):
        if _is_sequence(sub):
            return type(sub)(_build(s) for s in sub)
        elif _is_mapping(sub):
            return type(sub)((key, _build(sub[key])) for key in sorted(sub.keys()))
        else:
            return next(it)

    result = _build(n)
    # Upstream raises if the flat list length doesn't match the leaf count.
    leftover = list(it)
    if leftover:
        raise ValueError("pack_as: too many elements for the given nest")
    return result


def for_each(f: Callable[[Any], None], n: Any) -> None:
    """Call ``f`` on each leaf for its side effects."""
    for leaf in flatten(n):
        f(leaf)
