"""Build a bounded, two-hop neighborhood from the movie knowledge graph."""

from __future__ import annotations

from rdflib.namespace import RDF, RDFS

from .catalog import CatalogService
from .vocabulary import CINE

ENTITY_TYPES = {
    "movie": (CINE.Movie, CINE.title, "Movie"),
    "actor": (CINE.Actor, RDFS.label, "Actor"),
    "director": (CINE.Director, RDFS.label, "Director"),
    "genre": (CINE.Genre, RDFS.label, "Genre"),
}
RELATIONS = (
    (CINE.hasActor, "has actor"),
    (CINE.directedBy, "directed by"),
    (CINE.hasGenre, "has genre"),
)
MAX_DEPTH = 2
MAX_NODES = 64
MAX_ROOT_NEIGHBORS = 12
MAX_BRANCH_NEIGHBORS = 4


class GraphNeighborhood:
    def __init__(self, catalog: CatalogService):
        self.catalog = catalog

    def run(self, entity_type: str, value: str) -> dict:
        value = value.strip()
        if entity_type not in ENTITY_TYPES:
            raise ValueError("Invalid entity type.")
        if not value:
            raise ValueError("Enter an entity name to explore.")
        if len(value) > 160:
            raise ValueError("Entity names must be 160 characters or fewer.")

        class_uri, label_predicate, _ = ENTITY_TYPES[entity_type]
        seed = next(
            (
                entity
                for entity in self.catalog.graph.subjects(RDF.type, class_uri)
                if str(self.catalog.graph.value(entity, label_predicate) or "").casefold()
                == value.casefold()
            ),
            None,
        )
        if seed is None:
            raise ValueError("No entity matches that name.")

        nodes = {
            seed: {"depth": 0, "parent": None, "via": ""},
        }
        edges = {}
        queue = [seed]
        truncated = False

        while queue:
            current = queue.pop(0)
            depth = nodes[current]["depth"]
            if depth >= MAX_DEPTH:
                continue

            candidates = self._neighbors(current)
            branch_limit = MAX_ROOT_NEIGHBORS if depth == 0 else MAX_BRANCH_NEIGHBORS
            if len(candidates) > branch_limit:
                truncated = True

            for subject, object_, predicate, relation in self._select_neighbors(
                current, candidates, branch_limit
            ):
                neighbor = object_ if subject == current else subject
                edge_key = (subject, predicate, object_)
                edges[edge_key] = relation
                if neighbor in nodes:
                    continue
                if len(nodes) >= MAX_NODES:
                    truncated = True
                    continue
                nodes[neighbor] = {
                    "depth": depth + 1,
                    "parent": current,
                    "via": relation,
                }
                queue.append(neighbor)

        node_rows = []
        for entity, details in nodes.items():
            kind, kind_label = self._entity_kind(entity)
            node_rows.append(
                {
                    "id": str(entity),
                    "label": self._entity_label(entity, kind),
                    "kind": kind,
                    "kindLabel": kind_label,
                    "depth": details["depth"],
                    "parent": str(details["parent"]) if details["parent"] is not None else None,
                    "via": details["via"],
                }
            )
        node_rows.sort(key=lambda node: (node["depth"], node["label"].casefold()))

        edge_rows = [
            {"source": str(subject), "target": str(object_), "relation": relation}
            for (subject, predicate, object_), relation in edges.items()
            if subject in nodes and object_ in nodes
        ]
        return {
            "root": str(seed),
            "nodes": node_rows,
            "edges": edge_rows,
            "truncated": truncated,
            "maxDepth": MAX_DEPTH,
        }

    def _select_neighbors(self, current, candidates, limit):
        ordered = sorted(
            candidates,
            key=lambda edge: self._node_order_key(edge[1] if edge[0] == current else edge[0]),
        )
        selected = []
        selected_kinds = set()
        for edge in ordered:
            neighbor = edge[1] if edge[0] == current else edge[0]
            kind, _ = self._entity_kind(neighbor)
            if kind not in selected_kinds:
                selected.append(edge)
                selected_kinds.add(kind)
                if len(selected) >= limit:
                    return selected
        for edge in ordered:
            if edge not in selected:
                selected.append(edge)
                if len(selected) >= limit:
                    break
        return selected

    def _neighbors(self, entity):
        neighbors = {}
        for predicate, relation in RELATIONS:
            for object_ in self.catalog.graph.objects(entity, predicate):
                neighbors[(entity, object_, predicate)] = (entity, object_, predicate, relation)
            for subject in self.catalog.graph.subjects(predicate, entity):
                neighbors[(subject, entity, predicate)] = (subject, entity, predicate, relation)
        return list(neighbors.values())

    def _entity_kind(self, entity):
        for kind, (class_uri, _, label) in ENTITY_TYPES.items():
            if (entity, RDF.type, class_uri) in self.catalog.graph:
                return kind, label
        return "entity", "Entity"

    def _entity_label(self, entity, kind):
        if kind == "movie":
            return str(self.catalog.graph.value(entity, CINE.title) or "Untitled")
        return self.catalog.label(entity)

    def _node_order_key(self, entity):
        kind, _ = self._entity_kind(entity)
        label = self._entity_label(entity, kind)
        if kind == "movie":
            try:
                rating = float(self.catalog.literal(entity, CINE.imdbRating, "0"))
            except ValueError:
                rating = 0.0
            return (0, -rating, label.casefold())
        return ({"actor": 1, "director": 2, "genre": 3}.get(kind, 4), label.casefold())
