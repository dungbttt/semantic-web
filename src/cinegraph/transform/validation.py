from __future__ import annotations

from pathlib import Path

from pyshacl import validate
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

SH = Namespace("http://www.w3.org/ns/shacl#")


def validate_graph(data_graph: Graph, shapes_path: Path) -> tuple[dict, Graph]:
    """Validate the generated graph and return a compact summary plus SHACL report graph."""
    shapes_graph = Graph()
    shapes_graph.parse(shapes_path, format="turtle")
    conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="none",
        abort_on_first=False,
        meta_shacl=False,
        advanced=False,
    )
    result_nodes = list(report_graph.subjects(RDF.type, SH.ValidationResult))
    issues = []
    for result in result_nodes[:10]:
        issues.append(
            {
                "focus_node": str(report_graph.value(result, SH.focusNode) or ""),
                "path": str(report_graph.value(result, SH.resultPath) or ""),
                "message": str(
                    report_graph.value(result, SH.resultMessage) or "SHACL constraint violation"
                ),
            }
        )
    return {
        "conforms": bool(conforms),
        "result_count": len(result_nodes),
        "issues": issues,
        "summary": str(report_text).splitlines()[0] if report_text else "",
    }, report_graph
