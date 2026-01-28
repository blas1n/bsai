"""Main CodeAgent class."""

import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

from ..graph.workflow import create_agent_graph, create_planning_agent_graph
from ..llm.client import create_llm
from ..logging import setup_logging
from ..tools.file import list_directory, read_file, write_file


class CodeAgent:
    """Code agent with file manipulation tools.

    Supports two modes:
    - simple: Direct tool-calling (Phase 1)
    - planning: Plan-and-execute (Phase 2)
    """

    def __init__(self, model: str = "gpt-4o-mini", mode: str = "planning"):
        """Initialize the code agent.

        Args:
            model: Model name for LLM
            mode: Agent mode - 'simple' or 'planning'
        """
        self.llm = create_llm(model)
        self.tools = [read_file, write_file, list_directory]
        self.mode = mode

        if mode == "planning":
            self.graph = create_planning_agent_graph(self.llm, self.tools)
        else:
            self.graph = create_agent_graph(self.llm, self.tools)

    def run(self, user_input: str) -> str:
        """Run the agent with user input.

        Args:
            user_input: User's request

        Returns:
            Agent's response
        """
        if self.mode == "planning":
            initial_state = {
                "messages": [HumanMessage(content=user_input)],
                "plan": None,
                "current_step_index": 0,
                "step_results": {},
                "replans_count": 0,
            }
        else:
            initial_state = {"messages": [HumanMessage(content=user_input)]}

        result = self.graph.invoke(initial_state)
        return str(result["messages"][-1].content)


if __name__ == "__main__":
    load_dotenv()
    setup_logging(level="DEBUG")

    mode = sys.argv[1] if len(sys.argv) > 1 else "planning"
    agent = CodeAgent(mode=mode)
    print(f"Code Agent Ready (mode={mode}). Type 'exit' to quit.")

    while True:
        user_input = input("\n> ")
        if user_input.lower() == "exit":
            break

        response = agent.run(user_input)
        print(f"\n{response}")
