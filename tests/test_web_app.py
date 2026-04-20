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
            Checkbox=_component_factory("Checkbox"),
            Markdown=_component_factory("Markdown"),
            Gallery=_component_factory("Gallery"),
            HTML=_component_factory("HTML"),
            Button=_component_factory("Button"),
            themes=_FakeThemes(),
            update=lambda **kwargs: kwargs,
        )


class WebAppTests(unittest.TestCase):
    def test_build_demo_constructs_tabular_and_history_qa_workbench(self):
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
        ), patch(
            "data_analysis_agent.web.app.load_history_qa_runs",
            return_value=([("run_demo | finance | accepted | 2026-04-14", "run_demo")], ["run_demo"]),
        ), patch(
            "data_analysis_agent.web.app.load_knowledge_base_status",
            return_value="<section>知识库状态 / 已收录文档</section>",
        ):
            demo = app.build_demo()

        self.assertIsInstance(demo, _FakeComponent)
        self.assertEqual(demo.component_type, "Blocks")
        self.assertEqual(demo.kwargs.get("title"), "学术数据智能体交互工作台")
        self.assertIn("theme", demo.kwargs)
        self.assertIn("css", demo.kwargs)
        self.assertIn("min-height:700px", demo.kwargs["css"].replace(" ", ""))

        text_fragments = [
            component.args[0]
            for component in _FakeComponent.instances
            if component.args and isinstance(component.args[0], str)
        ]
        self.assertTrue(any("上传表格" in text or "CSV / Excel 表格分析" in text for text in text_fragments))
        self.assertTrue(any("知识库状态 / 已收录文档" in text for text in text_fragments))

        tab_labels = [component.args[0] for component in _FakeComponent.instances if component.component_type == "Tab"]
        for expected_tab in ["开始分析", "查看结果", "历史与追问"]:
            self.assertIn(expected_tab, tab_labels)

        labels = [component.kwargs.get("label") for component in _FakeComponent.instances]
        self.assertIn("上传表格数据", labels)
        self.assertIn("可沉淀的参考资料（可选，多文件）", labels)
        self.assertIn("输出深度", labels)
        self.assertIn("检查图表表达", labels)
        self.assertIn("参考历史经验", labels)
        self.assertIn("追问范围", labels)
        self.assertIn("追问方式", labels)
        self.assertNotIn("文档解析模式", labels)
        self.assertNotIn("主表选择", labels)

        file_components = [component for component in _FakeComponent.instances if component.component_type == "File"]
        upload_component = next(component for component in file_components if component.kwargs.get("label") == "上传表格数据")
        self.assertEqual(upload_component.kwargs["file_types"], [".csv", ".xls", ".xlsx"])

        button_components = [
            component
            for component in _FakeComponent.instances
            if component.component_type == "Button" and component.click_calls
        ]
        button_labels = [component.args[0] for component in button_components if component.args]
        self.assertIn("开始分析", button_labels)
        self.assertIn("刷新历史与知识库", button_labels)
        self.assertIn("开始追问", button_labels)
        self.assertNotIn("预览候选表", button_labels)

        run_button = next(component for component in button_components if component.args and component.args[0] == "开始分析")
        history_qa_button = next(component for component in button_components if component.args and component.args[0] == "开始追问")
        self.assertFalse(run_button.click_calls[0][1]["api_name"])
        self.assertFalse(history_qa_button.click_calls[0][1]["api_name"])

        quality_mode = next(
            component
            for component in _FakeComponent.instances
            if component.component_type == "Dropdown" and component.kwargs.get("label") == "输出深度"
        )
        self.assertEqual(len(quality_mode.change_calls), 1)


if __name__ == "__main__":
    unittest.main()
