"""Input handling for isotope-agents TUI.

This module provides input reading capabilities with prompt_toolkit integration
for enhanced user experience during streaming, including steering and follow-up
commands in Claude Code style.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Optional prompt_toolkit support (Claude Code style input during streaming)
# ---------------------------------------------------------------------------

try:
    from prompt_toolkit import PromptSession as _PromptSession
    from prompt_toolkit.application import Application as _Application
    from prompt_toolkit.buffer import Buffer as _Buffer
    from prompt_toolkit.document import Document as _Document
    from prompt_toolkit.key_binding import KeyBindings as _KeyBindings
    from prompt_toolkit.layout.containers import HSplit as _HSplit
    from prompt_toolkit.layout.containers import Window as _Window
    from prompt_toolkit.layout.controls import BufferControl as _BufferControl
    from prompt_toolkit.layout.controls import FormattedTextControl as _FormattedTextControl
    from prompt_toolkit.layout.layout import Layout as _Layout
    from prompt_toolkit.layout.processors import BeforeInput as _BeforeInput
    from prompt_toolkit.patch_stdout import patch_stdout as _patch_stdout

    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


class StreamInputHandler:
    """Handle user input during streaming with prompt_toolkit support."""

    def __init__(self) -> None:
        self._prefill_text = ""  # carry partially typed input between prompts
        self._prompt_session: Any = _PromptSession() if HAS_PROMPT_TOOLKIT else None
        self._stream_prompt_app: Any = None
        self._stream_prompt_buffer: Any = None

    def create_stream_prompt_app(self, agent: Any) -> tuple[Any, Any]:
        """Create the in-stream footer input application."""
        done = asyncio.Event()
        app: Any = None

        def _accept(buf: Any) -> bool:
            if app is not None and not done.is_set():
                done.set()
                app.exit(result=buf.text)
            return True

        buffer = _Buffer(
            document=_Document(
                text=self._prefill_text,
                cursor_position=len(self._prefill_text),
            ),
            multiline=False,
            accept_handler=_accept,
        )
        bindings = _KeyBindings()

        @bindings.add("c-c")
        def _abort(_event: Any) -> None:
            if agent is not None:
                agent.abort()
            if app is not None and not done.is_set():
                done.set()
                app.exit(result="/abort")

        app = _Application(
            layout=_Layout(
                _HSplit(
                    [
                        _Window(
                            content=_FormattedTextControl(
                                [("fg:#555555", "─" * 50)],
                            ),
                            height=1,
                            dont_extend_height=True,
                        ),
                        _Window(
                            content=_BufferControl(
                                buffer=buffer,
                                input_processors=[
                                    _BeforeInput([("fg:#5599ff bold", "› ")]),
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
        return app, buffer

    def close_stream_prompt(self, *, preserve_buffer: bool) -> None:
        """Close the active in-stream prompt application."""
        if preserve_buffer and self._stream_prompt_buffer is not None:
            self._prefill_text = self._stream_prompt_buffer.text
        if self._stream_prompt_app is not None:
            with contextlib.suppress(Exception):
                self._stream_prompt_app.exit(result=None)

    def handle_stream_input_line(
        self,
        line: str,
        agent: Any,
        *,
        prompt_toolkit: bool,
        print_stream_notice: Any,
    ) -> tuple[bool, str | None]:
        """Handle one line of user input while streaming.

        Returns:
            Tuple of (should_stop_reading, steer_text)
        """
        line = line.strip()
        if not line:
            return False, None

        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "/follow" and arg and agent:
                agent.follow_up(arg)
                print_stream_notice(
                    f"follow-up queued: {arg}",
                    prompt_toolkit=prompt_toolkit,
                    style="tool",
                )
            elif cmd == "/abort" and agent:
                agent.abort()
                print_stream_notice(
                    "aborting...",
                    prompt_toolkit=prompt_toolkit,
                    style="warn",
                )
                return True, None
            elif cmd in ("/follow", "/steer") and not arg:
                print_stream_notice(
                    f"usage: {cmd} <message>",
                    prompt_toolkit=prompt_toolkit,
                    style="warn",
                )
            return False, None

        # Non-command input is steering
        return True, line

    async def read_input_during_stream(
        self,
        agent: Any,
        is_streaming_check: Any,
        handle_input_callback: Any,
    ) -> None:
        """Read input concurrently during streaming.

        Uses prompt_toolkit when available for a visible input prompt at the
        bottom of the terminal (like Claude Code). Falls back to readline.

        Any text input (no '/' prefix) is treated as steering.
        Only /follow and /abort are explicit commands.
        """
        if HAS_PROMPT_TOOLKIT and self._prompt_session is not None:
            return await self._read_input_prompt_toolkit(
                agent, is_streaming_check, handle_input_callback
            )
        return await self._read_input_readline(
            agent, is_streaming_check, handle_input_callback
        )

    async def _read_input_prompt_toolkit(
        self,
        agent: Any,
        is_streaming_check: Any,
        handle_input_callback: Any,
    ) -> None:
        """Read input using prompt_toolkit (visible prompt at bottom)."""
        app, buffer = self.create_stream_prompt_app(agent)
        self._stream_prompt_app = app
        self._stream_prompt_buffer = buffer
        try:
            while is_streaming_check():
                line = await app.run_async()
                if line is None:
                    return
                if handle_input_callback(line, prompt_toolkit=True):
                    return
        except asyncio.CancelledError:
            if self._stream_prompt_buffer is not None:
                self._prefill_text = self._stream_prompt_buffer.text
            self.close_stream_prompt(preserve_buffer=False)
            raise
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            self._stream_prompt_app = None
            self._stream_prompt_buffer = None

    async def _read_input_readline(
        self,
        agent: Any,
        is_streaming_check: Any,
        handle_input_callback: Any,
    ) -> None:
        """Read input using readline (fallback when prompt_toolkit unavailable)."""
        loop = asyncio.get_event_loop()
        while is_streaming_check():
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, OSError):
                break

            if not is_streaming_check():
                break

            if handle_input_callback(line, prompt_toolkit=False):
                return

    async def get_user_input(self, prompt: str, default: str = "") -> str:
        """Get user input with optional default value."""
        loop = asyncio.get_event_loop()

        if HAS_PROMPT_TOOLKIT and self._prompt_session is not None:
            from prompt_toolkit.formatted_text import HTML
            return await self._prompt_session.prompt_async(
                HTML(prompt),
                default=default or self._prefill_text,
            )
        else:
            print(prompt, end="", flush=True)
            try:
                return await loop.run_in_executor(None, input)
            except (EOFError, KeyboardInterrupt):
                return ""

    def set_prefill_text(self, text: str) -> None:
        """Set text to prefill in the next input prompt."""
        self._prefill_text = text

    def clear_prefill_text(self) -> None:
        """Clear the prefill text."""
        self._prefill_text = ""

    @property
    def has_prompt_toolkit(self) -> bool:
        """Check if prompt_toolkit is available."""
        return HAS_PROMPT_TOOLKIT

    @property
    def patch_stdout(self) -> Any:
        """Get patch_stdout context manager if available."""
        return _patch_stdout if HAS_PROMPT_TOOLKIT else contextlib.nullcontext