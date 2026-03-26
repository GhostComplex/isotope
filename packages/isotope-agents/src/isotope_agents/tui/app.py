"""Main TUI application for isotope-agents.

This module provides the interactive terminal user interface for isotope-agents,
with model selection, command handling, and streaming response support with
Claude Code style steering.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from collections.abc import AsyncGenerator

# Bypass system HTTP proxies (e.g. Clash) for localhost
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")

from isotope_core.providers.proxy import ProxyProvider
from isotope_core.types import AgentEvent, AssistantMessage

from isotope_agents.agent import IsotopeAgent
from isotope_agents.presets import CODING
from isotope_agents.session import SessionStore

from .commands import CommandHandler, CommandResult, TUIState
from .input import StreamInputHandler
from .render import _print, _print_inline, _StreamBuffer, render_markdown, render_tool_output

PROXY_BASE_URL = "http://localhost:4141/v1"
DEFAULT_MODEL = "claude-opus-4.6"

# Workspace directory — all relative file paths are resolved against this.
WORKSPACE = os.getcwd()


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------

async def _fetch_models(base_url: str) -> list[str]:
    """Fetch available models from the proxy."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base_url}/models")
            resp.raise_for_status()
            data = resp.json()
            models: list[str] = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                if mid:
                    models.append(mid)
            return sorted(models)
    except Exception as exc:
        _print(f"Warning: could not fetch models: {exc}", style="warn")
        return []


# ---------------------------------------------------------------------------
# Main TUI
# ---------------------------------------------------------------------------

class TUI:
    """Interactive TUI for isotope-agents."""

    def __init__(self) -> None:
        self._state = TUIState(model=DEFAULT_MODEL, preset=CODING)
        self._command_handler = CommandHandler(self._state)
        self.agent: IsotopeAgent | None = None
        self.session_store = SessionStore()
        self._is_streaming = False
        self._stream_task: asyncio.Task[None] | None = None
        self._steer_text: str | None = None  # set by input reader on steer
        self._input_handler = StreamInputHandler()
        self.resume_session_id: str | None = None  # session to resume

    # -- convenience accessors for state fields used throughout the class ----

    @property
    def model(self) -> str:
        return self._state.model

    @model.setter
    def model(self, value: str) -> None:
        self._state.model = value

    @property
    def preset(self) -> object:
        return self._state.preset

    @property
    def tools_enabled(self) -> bool:
        return self._state.tools_enabled

    @property
    def debug(self) -> bool:
        return self._state.debug

    @property
    def custom_system_prompt(self) -> str | None:
        return self._state.custom_system_prompt

    @custom_system_prompt.setter
    def custom_system_prompt(self, value: str | None) -> None:
        self._state.custom_system_prompt = value

    @property
    def total_input_tokens(self) -> int:
        return self._state.total_input_tokens

    @total_input_tokens.setter
    def total_input_tokens(self, value: int) -> None:
        self._state.total_input_tokens = value

    @property
    def total_output_tokens(self) -> int:
        return self._state.total_output_tokens

    @total_output_tokens.setter
    def total_output_tokens(self, value: int) -> None:
        self._state.total_output_tokens = value

    def _print_stream_notice(
        self,
        message: str,
        *,
        prompt_toolkit: bool,
        style: str,
    ) -> None:
        """Print a status line while the model is streaming."""
        if prompt_toolkit:
            print(f"  [{message}]", flush=True)
        else:
            _print(f"\n  [{message}]", style=style)

    def _handle_stream_input_line(self, line: str, *, prompt_toolkit: bool) -> bool:
        """Handle one line of user input while streaming.

        Returns True when the caller should stop reading more input.
        """
        should_stop, steer_text = self._input_handler.handle_stream_input_line(
            line, self.agent, prompt_toolkit=prompt_toolkit,
            print_stream_notice=self._print_stream_notice
        )

        if steer_text:
            self._steer_text = steer_text
            self._cancel_stream()

        return should_stop

    async def _consume_stream_events(
        self,
        gen: AsyncGenerator[AgentEvent, None],
        *,
        prompt_toolkit: bool,
        buf: _StreamBuffer | None,
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
                        _print(f"  [{event.type}]", style="dim")

                if event.type == "message_update":
                    delta = getattr(event, "delta", None)
                    if delta:
                        if buf:
                            buf.write(delta)
                        else:
                            _print_inline(delta, style="model")

                elif event.type == "tool_start":
                    tool_name = getattr(event, "tool_name", "?")
                    if buf:
                        buf.flush()
                        print(f"  [calling {tool_name}]")
                    else:
                        _print(f"\n  [calling {tool_name}]", style="tool")

                elif event.type == "tool_end":
                    tool_name = getattr(event, "tool_name", "?")
                    tool_output = getattr(event, "output", "")
                    is_error = getattr(event, "is_error", False)

                    if buf:
                        buf.flush()

                    # Use rich rendering for tool output
                    render_tool_output(tool_name, tool_output, is_error)

                elif event.type == "message_end":
                    # Render the completed assistant message as markdown
                    message = getattr(event, "message", None)
                    if isinstance(message, AssistantMessage) and message.text:
                        if buf:
                            buf.flush()
                        # Clear any buffered content and render as markdown
                        render_markdown(message.text)

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
                            _print(f"\n  [steer applied, turn {turn}]", style="tool")

                elif event.type == "follow_up":
                    if self.debug:
                        turn = getattr(event, "turn_number", "?")
                        if buf:
                            buf.flush()
                            print(f"  [follow-up applied, turn {turn}]")
                        else:
                            _print(f"\n  [follow-up applied, turn {turn}]", style="tool")

                elif event.type == "agent_end":
                    reason = getattr(event, "reason", "completed")
                    if reason != "completed" and self.debug:
                        if buf:
                            buf.flush()
                            print(f"  [ended: {reason}]")
                        else:
                            _print(f"\n  [ended: {reason}]", style="dim")

        except asyncio.CancelledError:
            # On cancellation (steering), discard the buffer.
            # The partial response is saved to history via partial_msg
            # so the LLM has context. Don't flush here because the
            # prompt_toolkit Application may already be torn down.
            if buf:
                buf.discard()
        except Exception as exc:
            if buf:
                buf.flush()
                print(f"Error: {exc}")
            else:
                _print(f"\nError: {exc}", style="err")

    async def _finish_stream_iteration(
        self,
        *,
        gen: AsyncGenerator[AgentEvent, None],
        buf: _StreamBuffer | None,
        done: set[asyncio.Task[None]],
        pending: set[asyncio.Task[None]],
        input_task: asyncio.Task[None],
    ) -> tuple[str, str | None, AssistantMessage | None]:
        """Finalize one streamed response iteration."""
        if input_task in pending:
            self._input_handler.close_stream_prompt(preserve_buffer=True)

        for task in pending:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        trailing_text = buf.drain() if buf else ""

        partial_msg = self.agent.core.state.stream_message if self.agent is not None else None

        # Explicitly close the generator so _run_loop's finally block runs
        # synchronously, resetting agent.state.is_streaming to False.
        await gen.aclose()

        stream_task = self._stream_task
        self._is_streaming = False
        self._stream_task = None

        steer_text = self._steer_text
        stream_completed_naturally = (
            stream_task is not None
            and stream_task in done
            and not stream_task.cancelled()
            and stream_task.exception() is None
        )
        if steer_text and stream_completed_naturally:
            self._input_handler.set_prefill_text(steer_text)
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

        # Drain the steering queue — we handle steering at the TUI level
        # by calling prompt() directly, so stale queue entries would
        # cause a duplicate redirect on the next agent_loop run.
        while not self.agent.core._steering_queue.empty():
            try:
                self.agent.core._steering_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Preserve the partial assistant response so the LLM knows what
        # it had already said before the user interrupted.
        if partial_msg is not None:
            self.agent.core.append_message(partial_msg)

        return steer_text

    def _cancel_stream(self) -> None:
        """Cancel the active stream task immediately (Claude Code style).

        Sends asyncio.CancelledError into the provider's stream generator,
        bypassing signal-based abort which has inherent polling latency.
        """
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()

    def _create_agent(self, session_id: str | None = None) -> IsotopeAgent:
        """Create a new agent with current settings.

        Args:
            session_id: Optional session ID to resume.
        """
        provider = ProxyProvider(
            model=self.model,
            base_url=PROXY_BASE_URL,
            api_key="not-needed",
        )

        # Use minimal preset when tools are disabled, otherwise use the current preset
        preset = "minimal" if not self.tools_enabled else self.preset

        agent = IsotopeAgent(
            provider=provider,
            preset=preset,
            model=self.model,
            system_prompt=self.custom_system_prompt,
            workspace=WORKSPACE,
            session_store=self.session_store,
            session_id=session_id,
        )

        # If resuming a session, load the history
        if session_id:
            try:
                entries = self.session_store.load(session_id)
                messages = self.session_store.entries_to_messages(entries)
                if messages:
                    agent.core.replace_messages(messages)
                    _print(f"Resumed session {session_id} with {len(messages)} messages", style="info")
            except FileNotFoundError:
                _print(f"Warning: Session {session_id} not found, starting fresh", style="warn")
            except Exception as e:
                _print(f"Warning: Failed to resume session {session_id}: {e}", style="warn")

        return agent

    def _rebuild_agent(self, *, keep_history: bool = True) -> None:
        """Rebuild the agent (e.g. after model / tool change)."""
        old_messages = self.agent.core.messages[:] if self.agent and keep_history else []
        old_session_id = self.agent.session_id if self.agent and keep_history else None
        self.agent = self._create_agent(old_session_id)
        if old_messages:
            self.agent.core.replace_messages(old_messages)

    async def _select_model(self, models: list[str]) -> str:
        """Let the user pick a model or accept the default."""
        if models:
            _print("\nAvailable models:", style="info")
            for i, m in enumerate(models, 1):
                marker = " (default)" if m == DEFAULT_MODEL else ""
                _print(f"  {i}. {m}{marker}", style="dim")

            choice = await self._input_handler.get_user_input(
                f"\nSelect model [Enter for {DEFAULT_MODEL}]: "
            )

            choice = choice.strip()
            if not choice:
                return DEFAULT_MODEL

            # Accept number or name
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models):
                    return models[idx]
            except ValueError:
                pass

            # Accept partial name match
            for m in models:
                if choice.lower() in m.lower():
                    return m

            _print(f"Unknown model '{choice}', using {DEFAULT_MODEL}", style="warn")
            return DEFAULT_MODEL
        return DEFAULT_MODEL

    async def _get_system_prompt(self) -> str:
        """Prompt user for system prompt."""
        prompt = await self._input_handler.get_user_input(
            "\nSystem prompt (Enter to skip): "
        )
        return prompt.strip()

    async def _handle_command(self, line: str) -> bool:
        """Handle a slash command. Returns True if should quit."""
        result: CommandResult = await self._command_handler.handle(line)

        # Render the message produced by the command handler.
        if result.message:
            for msg_line in result.message.split("\n"):
                _print(msg_line, style=result.style)

        # Execute follow-up actions that need I/O or the agent.
        if result.action == "rebuild_agent":
            self._rebuild_agent()
        elif result.action == "rebuild_agent_clear":
            self._rebuild_agent(keep_history=False)
            if self.agent and self.agent.session_id:
                _print(f"New session: {self.agent.session_id}", style="info")
        elif result.action == "compact":
            await self._execute_compact()
        elif result.action == "history":
            if self.agent:
                msg_count = len(self.agent.core.messages)
                _print(f"Messages: {msg_count}", style="info")
        elif result.action == "sessions":
            await self._execute_sessions()

        return result.should_quit

    async def _execute_compact(self) -> None:
        """Execute the /compact action (requires agent)."""
        if self.agent is None:
            _print("No active agent. Send a message first.", style="warn")
            return
        try:
            result = await self.agent.compact()
            if result.messages_compacted > 0:
                saved = result.tokens_before - result.tokens_after
                _print(
                    f"Compacted {result.messages_compacted} messages, "
                    f"saved ~{saved} tokens. "
                    f"Files: read={result.files_read}, modified={result.files_modified}",
                    style="info",
                )
            else:
                _print("Nothing to compact (too few messages).", style="info")
        except Exception as e:
            _print(f"Compaction failed: {e}", style="warn")

    async def _execute_sessions(self) -> None:
        """Execute the /sessions action (requires session store)."""
        try:
            sessions = self.session_store.list_sessions()
            if not sessions:
                _print("No sessions found.", style="info")
                return

            # Limit to 10 sessions for inline display
            sessions = sessions[:10]

            _print("Recent sessions:", style="info")
            _print(f"{'ID':<8} {'Started':<19} {'Messages':<8} {'Last message'}", style="dim")
            _print("-" * 80, style="dim")

            for session in sessions:
                # Format timestamp to remove timezone and seconds
                started_str = session.started_at[:19].replace('T', ' ')
                last_msg_preview = session.last_message_preview[:40] + ("..." if len(session.last_message_preview) > 40 else "")

                _print(f"{session.id:<8} {started_str:<19} {session.message_count:<8} {last_msg_preview}", style="dim")

        except Exception as e:
            _print(f"Error listing sessions: {e}", style="warn")

    async def _read_input_during_stream(self) -> None:
        """Read input concurrently during streaming."""
        await self._input_handler.read_input_during_stream(
            self.agent,
            lambda: self._is_streaming,
            self._handle_stream_input_line,
        )

    async def _send_message(self, text: str) -> None:
        """Send a user message and stream the response with concurrent input.

        Claude Code style steering: any text typed during streaming cancels the
        current response immediately and starts a new turn with that text.
        The partial assistant response is preserved in history so the LLM has
        context of what it already said.
        """
        if self.agent is None:
            session_id = self.resume_session_id if hasattr(self, 'resume_session_id') else None
            self.agent = self._create_agent(session_id)
        assert self.agent is not None

        current_text = text

        # patch_stdout wraps the entire streaming loop so that print() output
        # renders above prompt_toolkit's input prompt (Claude Code style).
        ctx = self._input_handler.patch_stdout()
        with ctx:
            while True:
                self._is_streaming = True
                self._steer_text = None
                trailing_text = ""

                # Hold a reference to the generator for explicit lifecycle control.
                # Just creating the generator doesn't execute code — it starts
                # running only when _consume iterates it.
                gen = self.agent.run(current_text)  # type: ignore[arg-type]

                # When prompt_toolkit is active, use print() for output so that
                # patch_stdout can route it above the input prompt (Rich Console
                # bypasses patch_stdout because it holds the original sys.stdout).
                _pt = self._input_handler.has_prompt_toolkit
                buf = _StreamBuffer() if _pt else None

                # Create input task FIRST so prompt_toolkit's Application starts
                # before streaming output arrives (patch_stdout needs the Application
                # running to route output above the prompt).
                input_task = asyncio.create_task(self._read_input_during_stream())
                self._stream_task = asyncio.create_task(
                    self._consume_stream_events(gen, prompt_toolkit=_pt, buf=buf)
                )

                # Wait for whichever finishes first.
                done, pending = await asyncio.wait(
                    {self._stream_task, input_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                trailing_text, steer_text, partial_msg = await self._finish_stream_iteration(
                    gen=gen,
                    buf=buf,
                    done=done,
                    pending=pending,
                    input_task=input_task,
                )

                if steer_text:
                    current_text = self._apply_steering_redirect(steer_text, partial_msg)
                    continue

                if trailing_text:
                    print(trailing_text)

                # Normal completion — exit loop
                break

        # Print newline after streamed text + token usage
        print()
        # Show usage for last assistant message
        assistant_msgs = [
            m for m in self.agent.core.messages if isinstance(m, AssistantMessage)
        ]
        if assistant_msgs:
            usage = assistant_msgs[-1].usage
            _print(
                f"[tokens: in={usage.input_tokens}, out={usage.output_tokens}]",
                style="dim",
            )

    async def run(self) -> None:
        """Main TUI loop."""
        _print("isotope-agents TUI v1.0", style="info")
        _print(f"Proxy: {PROXY_BASE_URL}", style="dim")
        _print(f"Workspace: {WORKSPACE}", style="dim")

        # Fetch and select model
        models = await _fetch_models(PROXY_BASE_URL)
        self.model = await self._select_model(models)
        _print(f"Model: {self.model}", style="model")

        # System prompt
        custom_prompt = await self._get_system_prompt()
        if custom_prompt:
            self.custom_system_prompt = custom_prompt
            _print(f"System prompt: {self.custom_system_prompt}", style="dim")
        else:
            _print(f"Using {self.preset.name} preset system prompt", style="dim")

        # Create agent (with session resuming if requested)
        if self.resume_session_id:
            self.agent = self._create_agent(self.resume_session_id)
        else:
            self.agent = self._create_agent()

        # Display session ID if available
        if self.agent.session_id:
            _print(f"Session: {self.agent.session_id}", style="info")

        _print("\nType your message (or /help for commands). Ctrl+C to quit.\n", style="dim")

        while True:
            try:
                if self._input_handler.has_prompt_toolkit:
                    _print("─" * 50, style="white")
                    line = await self._input_handler.get_user_input(
                        "<style fg='#5599ff'><b>› </b></style>"
                    )
                    self._input_handler.clear_prefill_text()
                else:
                    _print_inline("> ", style="user")
                    line = await self._input_handler.get_user_input("")
            except (EOFError, KeyboardInterrupt):
                print()
                _print("Bye!", style="info")
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                should_quit = await self._handle_command(line)
                if should_quit:
                    break
                continue

            await self._send_message(line)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the TUI."""
    try:
        asyncio.run(TUI().run())
    except KeyboardInterrupt:
        print("\nBye!")
        sys.exit(0)


if __name__ == "__main__":
    main()