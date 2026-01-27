"""LLM client configuration."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def create_llm(model: str = "gpt-4o-mini") -> BaseChatModel:
    """Create a LangChain ChatModel instance.

    Args:
        model: Model name to use. Supports OpenAI models (gpt-*) and
               Anthropic models (claude-*).

    Returns:
        Configured ChatModel instance
    """
    if model.startswith("claude"):
        return ChatAnthropic(model=model, temperature=0)
    return ChatOpenAI(model=model, temperature=0)
