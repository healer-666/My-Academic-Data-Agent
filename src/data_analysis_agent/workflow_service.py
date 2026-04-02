"""Workflow orchestration helpers layered above the hello-agents runner."""

from __future__ import annotations

from dataclasses import dataclass, field

from .events import EventRecorder
from .runtime_models import WorkflowState


@dataclass
class WorkflowTracker:
    recorder: EventRecorder
    states: list[WorkflowState] = field(default_factory=list)
    current_state: WorkflowState | None = None

    def transition(self, state: WorkflowState) -> None:
        self.current_state = state
        self.states.append(state)
        self.recorder.emit("workflow_state_changed", workflow_state=state, state=state.value)

    def snapshot(self) -> tuple[WorkflowState, ...]:
        return tuple(self.states)
