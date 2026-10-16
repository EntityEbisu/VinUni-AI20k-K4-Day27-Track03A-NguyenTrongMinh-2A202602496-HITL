import pytest

from common.schemas import AUTO_APPROVE_THRESHOLD, ESCALATE_THRESHOLD
from exercises.exercise_1_confidence import build_graph, node_route
from tests.fakes import make_analysis


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.95, "auto_approve"),
        (AUTO_APPROVE_THRESHOLD, "auto_approve"),   # biên: 0.73 -> auto
        (0.72, "human_approval"),                   # biên: 0.72 -> human
        (0.65, "human_approval"),
        (ESCALATE_THRESHOLD, "human_approval"),     # biên: 0.58 -> human (không escalate)
        (0.57, "escalate"),
        (0.10, "escalate"),
    ],
)
def test_node_route_maps_confidence_to_branch(confidence, expected):
    state = {"analysis": make_analysis(confidence)}
    assert node_route(state)["decision"] == expected


def test_ex1_graph_contains_all_nodes():
    graph = build_graph().get_graph()
    assert {"fetch_pr", "analyze", "route", "auto_approve", "human_approval", "escalate"} <= set(
        graph.nodes
    )
