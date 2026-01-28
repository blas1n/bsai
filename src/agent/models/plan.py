"""Plan and PlanStep models for structured planning."""

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """A single step in a multi-step plan."""

    step_number: int = Field(description="Step number (1-indexed)")
    action: str = Field(
        description="Action to perform: read_file, write_file, list_directory, or analyze"
    )
    description: str = Field(description="What this step does")
    input_data: str = Field(description="Input data or target for this step")
    expected_output: str = Field(description="Expected result of this step")


class Plan(BaseModel):
    """A complete execution plan."""

    goal: str = Field(description="The user's original request")
    reasoning: str = Field(description="Why this plan was chosen")
    steps: list[PlanStep] = Field(description="Steps to execute in order")

    @property
    def total_steps(self) -> int:
        """Return the total number of steps in the plan."""
        return len(self.steps)
