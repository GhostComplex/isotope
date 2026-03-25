"""Main TUI application for isotope-agents.

Lifted from isotope-core tui/main.py and modularized. Provides an interactive
chat interface with streaming, Claude Code-style steering, and slash commands.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator

from isotopo_core.types import AgentEvent, AssistantMessage

from isotope_agents.agent import IsotopeAgent
from isotope_agents.tui.commands import handle_command, handle_stream_input_line
from isotope_agents.tui.input import HAS_PROMPT_TOOLKIT, InputHandler, patch_stdout
from isotope_agents.tui.output import StreamBuffer, tui_print, tui_print_inline


class TUIApp:
    """Interactive TUI application for isotope-agents.

    Provides Claude Code-style interaction with streaming responses,
    steering (type during streaming to redirect), follow-ups, and slash commands.
    """

    def __init__(self, isotope_agent: IsotopeAgent) -> None:
        """Initialize the TUI app.

        Args:
            isotope_agent: The IsotopeAgent to interact with.
        """
        self.isotope_agent = isotope_agent
        self.tools_enabled = len(isotope_agent.tools) > 0
        self.debug = False
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        self._is_streaming = False
        self._stream_task: asyncio.Task[None] | None = None
        self.steer_text: str | None = None
        self._input = InputHandler()

    def cancel_stream(self) -> None:
        """Cancel the active stream task immediately (Claude Code style)."""
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()

    async def _consume_stream_events(
        self,
        gen: AsyncGenerator[AgentEvent, None],
        *,
        prompt_toolkit: bool,
        buf: StreamBuffer | None,
    ) -> None:
        """Consume agent events for a single streamed response."""
        if prompt_toolkit:
            await asyncio.sleep(0)
        try:
            async for event in gen:
                if self.debug:
                    if buf:
                        buf.flush()
                        print(f"  [{event.type}]")
                    else:
                        tui_print(f"  [{event.type}]", style="dim")

                if event.type == "message_update":
                    delta = getattr(event, "delta", None)
                    if delta:
                        if buf:
                            buf.write(delta)
                        else:
                            tui_print_inline(delta, style="model")

                elif event.type == "tool_start":
                    tool_name = getattr(event, "tool_name", "?")
                    if buf:
                        buf.flush()
                        print(f"  [calling {tool_name}]")
                    else:
                        tui_print(f"\n  [calling {tool_name}]", style="tool")

                elif event.type == "tool_end":
                    is_error = getattr(event, "is_error", False)
                    if is_error:
                        if buf:
                            buf.flush()
                            print("  [tool error]")
                        else:
                            tui_print("  [tool error]", style="err")

                elif event.type == "turn_end":
                    msg = getattr(event, "message", None)
                    if isinstance(msg, AssistantMessage):
                        self.total_input_tokens += msg.usage.input_tokens
                        self.total_output_tokens += msg.usage.output_tokens

                elif event.type == "steer":
                    if self.debug:
                        turn = getattr(event, "turn_number", "?")
                        if buf:
                            buf.flush()
                            print(f"  [steer applied, turn {turn}]")
                        else:
                            tui_print(f"\n  [steer applied, turn {turn}]", style="tool")

                elif event.type == "follow_up":
                    if self.debug:
                        turn = getattr(event, "turn_number", "?")
                        if buf:
                            buf.flush()
                            print(f"  [follow-up applied, turn {turn}]")
                        else:
                            tui_print(f"\n  [follow-up applied, turn {turn}]", style="tool")

                elif event.type == "agent_end":
                    reason = getattr(event, "reason", "completed")
                    if reason != "completed" and self.debug:
                        if buf:
                            buf.flush()
                            print(f"  [ended: {reason}]")
                        else:
                            tui_print(f"\n  [ended: {reason}]", style="dim")

        except asyncio.CancelledError:
            if buf:
                buf.discard()
        except Exception as exc:
            if buf:
                buf.flush()
                print(f"Error: {exc}")
            else:
                tui_print(f"\nError: {exc}", style="err")

    async def _finish_stream_iteration(
        self,
        *,
        gen: AsyncGenerator[AgentEvent, None],
        buf: StreamBuffer | None,
        done: set[asyncio.Task[None]],
        pending: set[asyncio.Task[None]],
        input_task: asyncio.Task[None],
    ) -> tuple[str, str | None, AssistantMessage | None]:
        """Finalize one streamed response iteration."""
        if input_task in pending:
            self._input.close_stream_prompt(preserve_buffer=True)

        for task in pending:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        trailing_text = buf.drain() if buf else ""

        agent = self.isotope_agent.agent
        partial_msg = agent.state.stream_message

        # Explicitly close the generator so _run_loop's finally block runs
        await gen.aclose()

        stream_task = self._stream_task
        self._is_streaming = False
        self._stream_task = None

        steer_text = self.steer_text
        stream_completed_naturally = (
            stream_task is not None
            and stream_task in done
            and not stream_task.cancelled()
            and stream_task.exception() is None
        )
        if steer_text and stream_completed_naturally:
            self._input.prefill_text = steer_text
            steer_text = None

        assistant_partial = partial_msg if isinstance(partial_msg, AssistantMessage) else None
        return trailing_text, steer_text, assistant_partial

    def _apply_steering_redirect(
        self,
        steer_text: str,
        partial_msg: AssistantMessage | None,
    ) -> str:
        """Apply a steering redirect after the current stream is interrupted."""
        print(f"  [→ {steer_text}]")

        agent = self.isotope_agent.agent

        # Drain the steering queue
        while not agent._steering_queue.empty():
            try:
                agent._steering_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Preserve partial assistant response for context
        if partial_msg is not None:
            agent.append_message(partial_msg)

        return steer_text

    def _handle_stream_line(self, line: str, *, prompt_toolkit: bool) -> bool:
        """Handle one line of input during streaming (delegate to commands)."""
        return handle_stream_input_line(self, line, prompt_toolkit=prompt_toolkit)

    async def _send_message(self, text: str) -> None:
        """Send a user message and stream the response with concurrent input.

        Claude Code style steering: any text typed during streaming cancels the
        current response immediately and starts a new turn with that text.
        """
        agent = self.isotope_agent.agent
        current_text = text

        ctx = patch_stdout() if HAS_PROMPT_TOOLKIT else contextlib.nullcontext()
        with ctx:
            while True:
                self._is_streaming = True
                self.steer_text = None
                trailing_text = ""

                gen = agent.prompt(current_text)  # type: ignore[arg-type]

                _pt = HAS_PROMPT_TOOLKIT
                buf = StreamBuffer() if _pt else None

                input_task = asyncio.create_task(
                    self._input.read_input_during_stream(
                        is_streaming_fn=lambda: self._is_streaming,
                        handle_line_fn=self._handle_stream_line,
                        abort_callback=lambda: agent.abort(),
                    )
                )
                self._stream_task = asyncio.create_task(
                    self._consume_stream_events(gen, prompt_toolkit=_pt, buf=buf)
                )

                done, pending = await asyncio.wait(
                    {self._stream_task, input_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                trailing_text, steer_text, partial_msg = (
                    await self._finish_stream_iteration(
                        gen=gen,
                        buf=buf,
                        done=done,
                        pending=pending,
                        input_task=input_task,
                    )
                )

                if steer_text:
                    current_text = self._apply_steering_redirect(steer_text, partial_msg)
                    continue

                if trailing_text:
                    print(trailing_text)

                break

        # Print newline after streamed text + token usage
        print()
        assistant_msgs = [
            m for m in agent.messages if isinstance(m, AssistantMessage)
        ]
        if assistant_msgs:
            usage = assistant_msgs[-1].usage
            tui_print(
                f"[tokens: in={usage.input_tokens}, out={usage.output_tokens}]",
                style="dim",
            )

    async def run(self) -> None:
        """Main TUI loop."""
        tui_print("isotope-agents TUI v0.1", style="info")
        tui_print(f"Model: {self.isotope_agent.model}", style="model")
        tui_print(f"Preset: {self.isotope_agent.preset.name}", style="dim")

        if self.tools_enabled:
            names = ", ".join(t.name for t in self.isotope_agent.tools)
            tui_print(f"Tools: {names}", style="dim")

        tui_print(
            "\nType your message (or /help for commands). Ctrl+C to quit.\n",
            style="dim",
        )

        while True:
            line = await self._input.read_idle_input()
            if line is None:
                print()
                tui_print("Bye!", style="info")
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                should_quit = await handle_command(self, line)
                if should_quit:
                    break
                continue

            await self._send_message(line)


async def run_tui(isotope_agent: IsotopeAgent) -> None:
    """Run the TUI with the given agent.

    Args:
        isotope_agent: The configured IsotopeAgent.
    """
    app = TUIApp(isotope_agent)
    await app.run()
