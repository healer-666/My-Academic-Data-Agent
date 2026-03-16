from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.web import app


class _FakeComponent:
    instances: list["_FakeComponent"] = []

    def __init__(self, component_type: str, *args, **kwargs):
        self.component_type = component_type
        self.args = args
        self.kwargs = kwargs
        self.change_calls = []
        self.click_calls = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def change(self, *args, **kwargs):
        self.change_calls.append((args, kwargs))

    def click(self, *args, **kwargs):
        self.click_calls.append((args, kwargs))

    def queue(self, *args, **kwargs):
        return self

    def launch(self, *args, **kwargs):
        return self


def _component_factory(component_type: str):
    def _factory(*args, **kwargs):
        return _FakeComponent(component_type, *args, **kwargs)

    return _factory


class _FakeTheme:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.set_kwargs = {}

    def set(self, **kwargs):
        self.set_kwargs.update(kwargs)
        return self


class _FakeThemes(types.SimpleNamespace):
    def __init__(self):
        super().__init__(
            Soft=lambda *args, **kwargs: _FakeTheme(*args, **kwargs),
            GoogleFont=lambda name: f"GoogleFont({name})",
        )


class _FakeGradio(types.SimpleNamespace):
    def __init__(self):
        super().__init__(
            Blocks=_component_factory("Blocks"),
            Row=_component_factory("Row"),
            Column=_component_factory("Column"),
            Group=_component_factory("Group"),
            Accordion=_component_factory("Accordion"),
            Tabs=_component_factory("Tabs"),
            Tab=_component_factory("Tab"),
            File=_component_factory("File"),
            Textbox=_component_factory("Textbox"),
            Dropdown=_component_factory("Dropdown"),
            Slider=_component_factory("Slider"),
            Number=_component_factory("Number"),
            Markdown=_component_factory("Markdown"),
            Gallery=_component_factory("Gallery"),
            HTML=_component_factory("HTML"),
            Button=_component_factory("Button"),
            themes=_FakeThemes(),
            update=lambda **kwargs: kwargs,
        )


class WebAppTests(unittest.TestCase):
    def test_build_demo_constructs_dashboard_layout_without_runtime_errors(self):
        _FakeComponent.instances = []
        fake_gradio = _FakeGradio()
        with patch("data_analysis_agent.web.app.gr", fake_gradio), patch(
            "data_analysis_agent.web.app.build_history_choices",
            return_value=([("run_demo | finance | 已通过", "/tmp/run_demo")], "/tmp/run_demo"),
        ), patch(
            "data_analysis_agent.web.app.load_history_record",
            return_value=(
                "<section>历史总览</section>",
                "## 历史报告",
                [],
                "<section>历史轨迹</section>",
                None,
                None,
                None,
            ),
        ):
            demo = app.build_demo()

        self.assertIsInstance(demo, _FakeComponent)
        self.assertEqual(demo.component_type, "Blocks")
        self.assertIn("theme", demo.kwargs)
        self.assertIn("css", demo.kwargs)
        self.assertIn("min-height: 700px", demo.kwargs["css"])
        self.assertNotIn("position: sticky", demo.kwargs["css"])

        text_fragments = [
            component.args[0]
            for component in _FakeComponent.instances
            if component.args and isinstance(component.args[0], str)
        ]
        self.assertTrue(any("Academic-Data-Agent 交互工作台" in text for text in text_fragments))
        self.assertTrue(any("运行总览" in text for text in text_fragments))
        self.assertTrue(any("历史记录" in text for text in text_fragments))

        column_components = [component for component in _FakeComponent.instances if component.component_type == "Column"]
        group_components = [component for component in _FakeComponent.instances if component.component_type == "Group"]
        self.assertGreaterEqual(len(column_components), 2)
        self.assertGreaterEqual(len(group_components), 1)

        labels = [component.kwargs.get("label") for component in _FakeComponent.instances]
        self.assertIn("报告质量档位", labels)
        self.assertIn("文档解析模式", labels)
        self.assertIn("视觉审稿", labels)
        self.assertIn("主表选择", labels)
        self.assertIn("历史运行记录", labels)

        file_components = [component for component in _FakeComponent.instances if component.component_type == "File"]
        upload_component = next(component for component in file_components if component.kwargs.get("label") == "数据文件")
        self.assertIn(".pdf", upload_component.kwargs["file_types"])

        logs_box = next(
            component for component in _FakeComponent.instances if component.component_type == "Textbox" and component.kwargs.get("label") == "运行事件流"
        )
        self.assertEqual(logs_box.kwargs["lines"], 30)
        self.assertIn("live-log-box", logs_box.kwargs["elem_classes"])

        button_components = [
            component
            for component in _FakeComponent.instances
            if component.component_type == "Button" and component.click_calls
        ]
        self.assertGreaterEqual(len(button_components), 3)
        run_button = next(component for component in button_components if component.args and component.args[0] == "开始分析")
        preview_button = next(component for component in button_components if component.args and component.args[0] == "预览候选表")
        self.assertFalse(run_button.click_calls[0][1]["api_name"])
        self.assertFalse(preview_button.click_calls[0][1]["api_name"])

        upload_component = next(
            component for component in file_components if component.kwargs.get("label") == "数据文件"
        )
        self.assertEqual(len(upload_component.change_calls), 1)
        self.assertFalse(upload_component.change_calls[0][1]["api_name"])


if __name__ == "__main__":
    unittest.main()
