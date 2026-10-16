"""Kiểm tra app.py import được và có các hàm renderer (không gọi mạng, không chạy graph)."""

import app as app_module


def test_app_module_exposes_renderers():
    assert hasattr(app_module, "render_approval_card")
    assert hasattr(app_module, "render_escalation_card")
    assert hasattr(app_module, "run_graph")
