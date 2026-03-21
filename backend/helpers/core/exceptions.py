"""Structured exception hierarchy for Jarvis."""

from __future__ import annotations


class JarvisError(Exception):
    """Base exception for all Jarvis-specific errors."""

    def __init__(self, message: str, error_code: str = "internal_error"):
        super().__init__(message)
        self.error_code = error_code


class ModelUnavailableError(JarvisError):
    """Raised when the Ollama model is unreachable or not loaded."""

    def __init__(self, message: str = "Model is not available"):
        super().__init__(message, error_code="model_unavailable")


class ToolExecutionError(JarvisError):
    """Raised when a tool call fails during agent execution."""

    def __init__(self, tool_name: str, message: str):
        super().__init__(f"Tool '{tool_name}' failed: {message}", error_code="tool_error")
        self.tool_name = tool_name


class ContextWindowExceededError(JarvisError):
    """Raised when the context window is exceeded even after compaction."""

    def __init__(self, message: str = "Context window exceeded"):
        super().__init__(message, error_code="context_exceeded")


class AgentRunError(JarvisError):
    """Raised when the agent runner fails."""

    def __init__(self, agent_name: str, message: str):
        super().__init__(f"Agent '{agent_name}' failed: {message}", error_code="agent_error")
        self.agent_name = agent_name
