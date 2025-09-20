import logging
import os
import sys
from typing import Any, Dict, List, Optional

try:
    # LangChain v0.3.x
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:  # pragma: no cover
    # Fallback for older versions
    from langchain.callbacks.base import BaseCallbackHandler  # type: ignore


class ColorFormatter(logging.Formatter):
    """ANSI color log formatter for console output."""

    COLORS = {
        logging.DEBUG: "\033[90m",     # Bright black (grey)
        logging.INFO: "\033[36m",      # Cyan
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, color: bool = True):
        default_fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        super().__init__(fmt or default_fmt, datefmt)
        # Detect TTY and NO_COLOR env
        no_color_env = os.environ.get("NO_COLOR") is not None
        self.color = color and sys.stdout.isatty() and not no_color_env

    def format(self, record: logging.LogRecord) -> str:
        if self.color:
            color = self.COLORS.get(record.levelno, "")
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            record.name = f"\033[94m{record.name}{self.RESET}"  # Blue for logger name
        return super().format(record)


class LangChainWorkflowLogger(BaseCallbackHandler):
    """Lightweight console logger for LangChain/LangGraph runs.

    Emits high-level events for LLM, chain, and tool execution so you can
    observe prompts, responses, and errors without requiring LangSmith.
    """

    def __init__(self, logger: Optional[logging.Logger] = None, prompt_preview_chars: int = 400):
        self.logger = logger or logging.getLogger("LangChainWorkflow")
        if not self.logger.handlers:
            file_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            color_fmt = ColorFormatter()

            # Console (colored)
            ch = logging.StreamHandler()
            ch.setFormatter(color_fmt)
            self.logger.addHandler(ch)

            # Optional: file handler can be added by the application if needed
            self.logger.setLevel(logging.INFO)
        self.prompt_preview_chars = prompt_preview_chars

    # LLM lifecycle
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        model = (serialized or {}).get("id") or (serialized or {}).get("name") or "LLM"
        try:
            p0 = prompts[0] if prompts else ""
            preview = str(p0)[: self.prompt_preview_chars]
        except Exception:
            preview = "<unavailable>"
        self.logger.info(f"[LLM start] model={model} prompt[0]={preview}")

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        try:
            usage = getattr(response, "llm_output", None)
            self.logger.info(f"[LLM end] usage={usage}")
        except Exception:
            self.logger.info("[LLM end]")

    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        self.logger.error(f"[LLM error] {error}")

    # Chain lifecycle
    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        name = (serialized or {}).get("id") or (serialized or {}).get("name") or "Chain"
        keys = list(inputs.keys()) if isinstance(inputs, dict) else []
        self.logger.info(f"[Chain start] {name} inputs={keys}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        keys = list(outputs.keys()) if isinstance(outputs, dict) else []
        self.logger.info(f"[Chain end] outputs={keys}")

    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        self.logger.error(f"[Chain error] {error}")

    # Tool lifecycle (if tools are used)
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name") or "tool"
        self.logger.info(f"[Tool start] {name} input={str(input_str)[:200]}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self.logger.info(f"[Tool end] output={str(output)[:200]}")

    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        self.logger.error(f"[Tool error] {error}")
