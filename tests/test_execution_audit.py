from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.execution_audit import audit_stage_execution
from data_analysis_agent.runtime_models import AgentStepTrace


class ExecutionAuditTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"audit_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_audit_passes_when_cleaned_data_is_saved_then_reloaded(self):
        case_dir = self._workspace_case_dir()
        raw_path = case_dir / "sample.csv"
        raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
        cleaned_path = case_dir / "outputs" / "run_demo" / "data" / "cleaned_data.csv"
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_path.write_text("a,b\n1,2\n", encoding="utf-8")
        traces = (
            AgentStepTrace(
                step_index=1,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\ndf = pd.read_csv(r"{raw_path.as_posix()}")\ndf.to_csv(r"{cleaned_path.as_posix()}", index=False)',
                tool_status="success",
            ),
            AgentStepTrace(
                step_index=2,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\ndf = pd.read_csv(r"{cleaned_path.as_posix()}")\nprint(df.shape)',
                tool_status="success",
            ),
        )

        result = audit_stage_execution(
            step_traces=traces,
            source_data_path=raw_path,
            cleaned_data_path=cleaned_path,
        )

        self.assertEqual(result.status, "passed")
        self.assertTrue(result.stage1_save_detected)
        self.assertTrue(result.stage2_cleaned_reload_detected)
        self.assertFalse(result.raw_data_reused_after_stage1)

    def test_audit_fails_when_cleaned_data_is_never_reloaded(self):
        case_dir = self._workspace_case_dir()
        raw_path = case_dir / "sample.csv"
        raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
        cleaned_path = case_dir / "outputs" / "run_demo" / "data" / "cleaned_data.csv"
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_path.write_text("a,b\n1,2\n", encoding="utf-8")
        traces = (
            AgentStepTrace(
                step_index=1,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\ndf = pd.read_csv(r"{raw_path.as_posix()}")\ndf.to_csv(r"{cleaned_path.as_posix()}", index=False)',
                tool_status="success",
            ),
        )

        result = audit_stage_execution(
            step_traces=traces,
            source_data_path=raw_path,
            cleaned_data_path=cleaned_path,
        )

        self.assertEqual(result.status, "failed")
        self.assertTrue(any("reloaded" in finding.message for finding in result.findings))

    def test_audit_fails_when_raw_data_is_reused_after_stage1(self):
        case_dir = self._workspace_case_dir()
        raw_path = case_dir / "sample.csv"
        raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
        cleaned_path = case_dir / "outputs" / "run_demo" / "data" / "cleaned_data.csv"
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_path.write_text("a,b\n1,2\n", encoding="utf-8")
        traces = (
            AgentStepTrace(
                step_index=1,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\ndf = pd.read_csv(r"{raw_path.as_posix()}")\ndf.to_csv(r"{cleaned_path.as_posix()}", index=False)',
                tool_status="success",
            ),
            AgentStepTrace(
                step_index=2,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\ndf = pd.read_csv(r"{raw_path.as_posix()}")\nprint(df.shape)',
                tool_status="success",
            ),
        )

        result = audit_stage_execution(
            step_traces=traces,
            source_data_path=raw_path,
            cleaned_data_path=cleaned_path,
        )

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.raw_data_reused_after_stage1)

    def test_audit_marks_dynamic_cleaned_reload_as_ambiguous(self):
        case_dir = self._workspace_case_dir()
        raw_path = case_dir / "sample.csv"
        raw_path.write_text("a,b\n1,2\n", encoding="utf-8")
        cleaned_path = case_dir / "outputs" / "run_demo" / "data" / "cleaned_data.csv"
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned_path.write_text("a,b\n1,2\n", encoding="utf-8")
        traces = (
            AgentStepTrace(
                step_index=1,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input=f'import pandas as pd\nclean_path = r"{cleaned_path.as_posix()}"\ndf = pd.read_csv(r"{raw_path.as_posix()}")\ndf.to_csv(clean_path, index=False)',
                tool_status="success",
            ),
            AgentStepTrace(
                step_index=2,
                raw_response="{}",
                action="call_tool",
                tool_name="PythonInterpreterTool",
                tool_input='import pandas as pd\nrun_dir = "outputs/run_demo"\ndf = pd.read_csv(run_dir + "/data/cleaned_data.csv")\nprint(df.shape)',
                tool_status="success",
            ),
        )

        result = audit_stage_execution(
            step_traces=traces,
            source_data_path=raw_path,
            cleaned_data_path=cleaned_path,
        )

        self.assertEqual(result.status, "ambiguous")


if __name__ == "__main__":
    unittest.main()
