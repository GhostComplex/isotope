"""Input handling for the isotope-agents TUI.

Provides prompt-toolkit integration for Claude Code-style input during
streaming, with fallback to readline when prompt-toolkit is unavailable.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Optional prompt_toolkit support
# ---------------------------------------------------------------------------

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.layout import Layout
    from prompt_toolkit.layout.processors import BeforeInput
    from prompt_toolkit.patch_stdout import patch_stdout

    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

    # Provide stubs so type hints don't fail at runtime
    class PromptSession:  # type: ignore[no-redef]
        """Stub for when prompt_toolkit is not installed."""

        async def prompt_async(self, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError

    def patch_stdout() -> Any:  # type: ignore[no-redef]
        """Stub for when prompt_toolkit is not installed."""
        return contextlib.nullcontext()


__all__ = [
    "HAS_PROMPT_TOOLKIT",
    "InputHandler",
    "PromptSession",
    "patch_stdout",
]


class InputHandler:
    """Manages input during both idle and streaming states.

    Handles prompt-toolkit integration for Claude Code-style visible input
    at the bottom of the terminal during streaming, with readline fallback.
    """

    def __init__(self) -> None:
        self.prefill_text: str = ""
        self._prompt_session: PromptSession | None = (
            PromptSession() if HAS_PROMPT_TOOLKIT else None
        )
        self._stream_prompt_app: Any = None
        self._stream_prompt_buffer: Any = None

    @property
    def has_prompt_toolkit(self) -> bool:
        """Check if prompt_toolkit is available."""
        return HAS_PROMPT_TOOLKIT

    async def read_idle_input(self) -> str | None:
        """Read input when the agent is idle (between messages).

        Returns:
            The user's input, or None if EOF/interrupt.
        """
        try:
            if HAS_PROMPT_TOOLKIT and self._prompt_session is not None:
                print("─" * 50)
                line = await self._prompt_session.prompt_async(
                    HTML("<style fg='#5599ff'><b>› </b></style>"),
                    default=self.prefill_text,
                )
                self.prefill_text = ""
                return line
            else:
                print("> ", end="", flush=True)
                loop = asyncio.get_event_loop()
                line = await loop.run_in_executor(None, input)
                return line
        except (EOFError, KeyboardInterrupt):
            return None

    def create_stream_prompt_app(
        self, abort_callback: Any
    ) -> tuple[Any, Any]:
        """Create the in-stream footer input application.

        Args:
            abort_callback: Callable to invoke on Ctrl-C (abort).

        Returns:
            Tuple of (Application, Buffer).
        """
        if not HAS_PROMPT_TOOLKIT:
            raise RuntimeError("prompt_toolkit is required for stream prompt")

        done = asyncio.Event()
        app: Any = None

        def _accept(buf: Any) -> bool:
            if app is not None and not done.is_set():
                done.set()
                app.exit(result=buf.text)
            return True

        buffer = Buffer(
            document=Document(
                text=self.prefill_text,
                cursor_position=len(self.prefill_text),
            ),
            multiline=False,
            accept_handler=_accept,
        )
        bindings = KeyBindings()

        @bindings.add("c-c")
        def _abort(_event: Any) -> None:
            abort_callback()
            if app is not None and not done.is_set():
                done.set()
                app.exit(result="/abort")

        app = Application(
            layout=Layout(
                HSplit(
                    [
                        Window(
                            content=FormattedTextControl(
                                [("fg:#555555", "─" * 50)],
                            ),
                            height=1,
                            dont_extend_height=True,
                        ),
                        Window(
                            content=BufferControl(
                                buffer=buffer,
                                input_processors=[
                                    BeforeInput([("fg:#5599ff bold", "› ")]),
                                ],
                            ),
                            height=1,
                            dont_extend_height=True,
                        ),
                    ]
                )
            ),
            key_bindings=bindings,
            erase_when_done=True,
            full_screen=False,
            mouse_support=False,
        )

        self._stream_prompt_app = app
        self._stream_prompt_buffer = buffer
        return app, buffer

    def close_stream_prompt(self, *, preserve_buffer: bool) -> None:
        """Close the active in-stream prompt application.

        Args:
            preserve_buffer: If True, save buffer text as prefill for next prompt.
        """
        if preserve_buffer and self._stream_prompt_buffer is not None:
            self.prefill_text = self._stream_prompt_buffer.text
        if self._stream_prompt_app is not None:
            with contextlib.suppress(Exception):
                self._stream_prompt_app.exit(result=None)
        self._stream_prompt_app = None
        self._stream_prompt_buffer = None

    async def read_stream_input_prompt_toolkit(
        self,
        is_streaming_fn: Any,
        handle_line_fn: Any,
        abort_callback: Any,
    ) -> None:
        """Read input using prompt_toolkit during streaming.

        Args:
            is_streaming_fn: Callable returning True while streaming is active.
            handle_line_fn: Callable to handle each input line. Returns True to stop.
            abort_callback: Callable to invoke on Ctrl-C.
        """
        app, buffer = self.create_stream_prompt_app(abort_callback)
        try:
            while is_streaming_fn():
                line = await app.run_async()
                if line is None:
                    return
                if handle_line_fn(line, prompt_toolkit=True):
                    return
        except asyncio.CancelledError:
            if self._stream_prompt_buffer is not None:
                self.prefill_text = self._stream_prompt_buffer.text
            self.close_stream_prompt(preserve_buffer=False)
            raise
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            self._stream_prompt_app = None
            self._stream_prompt_buffer = None

    async def read_stream_input_readline(
        self,
        is_streaming_fn: Any,
        handle_line_fn: Any,
    ) -> None:
        """Read input using readline during streaming (fallback).

        Args:
            is_streaming_fn: Callable returning True while streaming is active.
            handle_line_fn: Callable to handle each input line. Returns True to stop.
        """
        loop = asyncio.get_event_loop()
        while is_streaming_fn():
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, OSError):
                break

            if not is_streaming_fn():
                break

            if handle_line_fn(line, prompt_toolkit=False):
                return

    async def read_input_during_stream(
        self,
        is_streaming_fn: Any,
        handle_line_fn: Any,
        abort_callback: Any,
    ) -> None:
        """Read input concurrently during streaming.

        Uses prompt_toolkit when available, falls back to readline.

        Args:
            is_streaming_fn: Callable returning True while streaming is active.
            handle_line_fn: Callable to handle each input line. Returns True to stop.
            abort_callback: Callable to invoke on Ctrl-C.
        """
        if HAS_PROMPT_TOOLKIT and self._prompt_session is not None:
            return await self.read_stream_input_prompt_toolkit(
                is_streaming_fn, handle_line_fn, abort_callback
            )
        return await self.read_stream_input_readline(is_streaming_fn, handle_line_fn)
