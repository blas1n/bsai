"""Main CodeAgent class."""

from langchain_core.messages import HumanMessage

from ..graph.workflow import create_agent_graph
from ..llm.client import create_llm
from ..tools.file import list_directory, read_file, write_file


class CodeAgent:
    """Simple code agent with file manipulation tools."""

    def __init__(self, model: str = "gpt-4o-mini"):
        """Initialize the code agent.

        Args:
            model: Model name to use for the LLM
        """
        self.llm = create_llm(model)
        self.tools = [read_file, write_file, list_directory]
        self.graph = create_agent_graph(self.llm, self.tools)

    def run(self, user_input: str) -> str:
        """Run the agent with user input.

        Args:
            user_input: User's request

        Returns:
            Agent's response
        """
        result = self.graph.invoke({"messages": [HumanMessage(content=user_input)]})
        return result["messages"][-1].content


if __name__ == "__main__":
    agent = CodeAgent()
    print("Code Agent Ready. Type 'exit' to quit.")

    while True:
        user_input = input("\n> ")
        if user_input.lower() == "exit":
            break

        response = agent.run(user_input)
        print(f"\n{response}")
