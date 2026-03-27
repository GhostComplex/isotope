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

from isotope_core.types import AgentEvent, AssistantMessage

from isotope_agents.agent import IsotopeAgent
from isotope_agents.config import (
    PROVIDER_DEFAULTS,
    IsotopeConfig,
    create_provider,
    fetch_available_models,
    load_agent_md,
    save_agent_md,
    save_config,
)
from isotope_agents.presets import CODING
from isotope_agents.session import SessionStore

from .commands import CommandHandler, CommandResult, TUIState
from .events import EventAction, process_event
from .input import StreamInputHandler
from .render import (
    _print,
    _print_inline,
    _StreamBuffer,
    render_markdown,
    render_tool_output,
)

PROVIDER_LABELS = {
    "anthropic": "Anthropic        (claude-opus-4.6, claude-sonnet-4.6, ...)",
    "openai": "OpenAI           (gpt-5.4, gpt-5.2, ...)",
    "minimax": "MiniMax CN       (MiniMax-M2.7, api.minimaxi.com)",
    "minimax-global": "MiniMax Global   (MiniMax-M2.7, api.minimax.io)",
    "proxy": "GitHub Copilot proxy  (localhost, LiteLLM, Ollama, ...)",
}

# Workspace directory — all relative file paths are resolved against this.
WORKSPACE = os.getcwd()


# ---------------------------------------------------------------------------
# Model listing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main TUI
# ---------------------------------------------------------------------------


class TUI:
    """Interactive TUI for isotope-agents."""

    def __init__(self) -> None:
        self._state = TUIState(model="", preset=CODING)
        self._command_handler = CommandHandler(self._state)
        self.agent: IsotopeAgent | None = None
        self.session_store = SessionStore()
        self._is_streaming = False
        self._stream_task: asyncio.Task[None] | None = None
        self._steer_text: str | None = None  # set by input reader on steer
        self._input_handler = StreamInputHandler()
        self.resume_session_id: str | None = None  # session to resume
        self._streamed_text: bool = False  # tracks if text deltas were emitted
        self.config: IsotopeConfig = IsotopeConfig()  # provider config

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

    @preset.setter
    def preset(self, value: object) -> None:
        self._state.preset = value

    @property
    def tools_enabled(self) -> bool:
        return self._state.tools_enabled

    @tools_enabled.setter
    def tools_enabled(self, value: bool) -> None:
        self._state.tools_enabled = value

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
            line,
            self.agent,
            prompt_toolkit=prompt_toolkit,
            print_stream_notice=self._print_stream_notice,
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
                actions = process_event(event, debug=self.debug)
                for action in actions:
                    self._apply_event_action(
                        action, buf=buf, prompt_toolkit=prompt_toolkit
                    )

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

    def _apply_event_action(
        self,
        action: EventAction,
        *,
        buf: _StreamBuffer | None,
        prompt_toolkit: bool,
    ) -> None:
        """Apply a single EventAction to the display."""
        if action.type == "text":
            self._streamed_text = True
            if buf:
                buf.write(action.content)
            else:
                _print_inline(action.content, style="model")

        elif action.type == "tool_start":
            if buf:
                buf.flush()
                print(f"  [calling {action.tool_name}]")
            else:
                _print(f"\n  [calling {action.tool_name}]", style="tool")

        elif action.type == "tool_end":
            if buf:
                buf.flush()
                # Rich Console bypasses patch_stdout, so render as plain text
                # when prompt_toolkit is active.
                error_marker = " (error)" if action.is_error else ""
                print(f"\n[{action.tool_name}{error_marker}]")
                stripped = action.content.strip()
                if stripped:
                    for line in stripped.splitlines():
                        print(f"  {line}")
                print()
            else:
                render_tool_output(action.tool_name, action.content, action.is_error)

        elif action.type == "message_end":
            # Skip markdown re-render when text was already streamed via
            # deltas — otherwise the response text is printed twice.
            if not self._streamed_text:
                if buf:
                    buf.flush()
                    # Rich Console bypasses patch_stdout; use plain print.
                    print(action.content)
                else:
                    render_markdown(action.content)

        elif action.type == "usage":
            self.total_input_tokens += action.input_tokens
            self.total_output_tokens += action.output_tokens

        elif action.type == "debug":
            if buf:
                buf.flush()
                print(f"  {action.content}")
            else:
                _print(f"  {action.content}", style="dim")

        # "none" actions are intentionally ignored.

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

        partial_msg = (
            self.agent.core.state.stream_message if self.agent is not None else None
        )

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

        assistant_partial = (
            partial_msg if isinstance(partial_msg, AssistantMessage) else None
        )
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
        provider = create_provider(self.model, self.config)

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
                    _print(
                        f"Resumed session {session_id} with {len(messages)} messages",
                        style="info",
                    )
            except FileNotFoundError:
                _print(
                    f"Warning: Session {session_id} not found, starting fresh",
                    style="warn",
                )
            except Exception as e:
                _print(
                    f"Warning: Failed to resume session {session_id}: {e}", style="warn"
                )

        return agent

    def _rebuild_agent(
        self,
        *,
        keep_history: bool = True,
        new_model: str | None = None,
        new_config: IsotopeConfig | None = None,
    ) -> None:
        """Rebuild the agent (e.g. after model / tool / provider change).

        Args:
            keep_history: Preserve existing message history.
            new_model: Switch to a different model.
            new_config: Switch to a different provider config.
        """
        if new_config is not None:
            self.config = new_config
            # Sync model from config when a full config swap happens
            # (e.g. /setup provider change) and no explicit new_model given.
            if new_model is None and new_config.model and new_config.model != "default":
                new_model = new_config.model
        if new_model is not None:
            self.model = new_model
            self._state.model = new_model
        old_messages = (
            self.agent.core.messages[:] if self.agent and keep_history else []
        )
        old_session_id = self.agent.session_id if self.agent and keep_history else None
        self.agent = self._create_agent(old_session_id)
        if old_messages:
            self.agent.core.replace_messages(old_messages)

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
        elif result.action == "switch_model":
            await self._execute_switch_model(self._state.model)
        elif result.action == "model_interactive":
            await self._execute_model_interactive()
        elif result.action == "setup_wizard":
            await self._execute_setup_wizard()
        elif result.action == "show_provider":
            self._execute_show_provider()
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
            _print(
                f"{'ID':<8} {'Started':<19} {'Messages':<8} {'Last message'}",
                style="dim",
            )
            _print("-" * 80, style="dim")

            for session in sessions:
                # Format timestamp to remove timezone and seconds
                started_str = session.started_at[:19].replace("T", " ")
                last_msg_preview = session.last_message_preview[:40] + (
                    "..." if len(session.last_message_preview) > 40 else ""
                )

                _print(
                    f"{session.id:<8} {started_str:<19} {session.message_count:<8} {last_msg_preview}",
                    style="dim",
                )

        except Exception as e:
            _print(f"Error listing sessions: {e}", style="warn")

    # -- /model, /setup, /provider actions -----------------------------------

    async def _execute_switch_model(self, model: str) -> None:
        """Switch model, persist to config, and rebuild agent."""
        self.config = IsotopeConfig(
            provider=self.config.provider,
            model=model,
            preset=self.config.preset,
            system_prompt=self.config.system_prompt,
            debug=self.config.debug,
            sessions_dir=self.config.sessions_dir,
            skills=self.config.skills,
            tools=self.config.tools,
            mcp_servers=self.config.mcp_servers,
        )
        save_config(self.config)
        self._rebuild_agent(new_model=model)
        _print(f"✓ Switched to {model} (saved to settings.json)", style="info")

    async def _execute_model_interactive(self) -> None:
        """Interactive model selection (no arg to /model)."""
        _print("\nFetching available models...", style="dim")
        models = await fetch_available_models(
            self.config.provider.base_url,
            api_key=self.config.provider.api_key,
            provider_type=self.config.provider.type,
        )

        if not models:
            _print("Could not fetch models. Use /model <name> directly.", style="warn")
            return

        # Separate overflow hint
        hint_entry = ""
        if models and models[-1].startswith("("):
            hint_entry = models.pop()

        # Current model first
        current = self.model
        if current in models:
            models.remove(current)
            models.insert(0, current)

        _print("Available models:", style="info")
        for i, m in enumerate(models, 1):
            suffix = " (current)" if m == current else ""
            _print(f"  {i}. {m}{suffix}", style="dim")
        if hint_entry:
            _print(f"  {hint_entry}", style="dim")

        choice = await self._input_handler.get_user_input(
            "\nModel [1] (Enter to cancel): "
        )
        choice = choice.strip()
        if not choice:
            _print("Cancelled.", style="dim")
            return

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(models)):
                idx = -1
        except ValueError:
            # Typed a model name directly
            await self._execute_switch_model(choice)
            return

        if idx >= 0:
            await self._execute_switch_model(models[idx])

    async def _execute_setup_wizard(self) -> None:
        """Run the /setup reconfigure wizard."""
        _print("\nCurrent configuration:", style="info")
        ptype = self.config.provider.type
        label = PROVIDER_LABELS.get(ptype, ptype)
        _print(f"  Provider: {label}", style="dim")
        _print(f"  Model: {self.model}", style="dim")
        sp_mode = self.config.system_prompt
        if sp_mode == "custom":
            _print("  System prompt: custom (agent.md)", style="dim")
        else:
            _print(f"  System prompt: {sp_mode}", style="dim")

        _print(
            "\nReconfigure: (p)rovider / (m)odel / (s)ystem prompt / (a)ll",
            style="info",
        )
        choice = await self._input_handler.get_user_input(
            "What to change? [a] (Enter to cancel): "
        )
        choice = choice.strip().lower()
        if not choice:
            _print("Cancelled.", style="dim")
            return

        if choice in ("a", "all"):
            # Full re-run of FRE wizard
            new_config = await self._run_setup_wizard()
            self._rebuild_agent(new_config=new_config)
            _print(f"✓ Reconfigured — {self.model}", style="info")
        elif choice in ("p", "provider"):
            new_config = await self._run_setup_wizard()
            self._rebuild_agent(new_config=new_config)
            _print(f"✓ Provider changed — {self.model}", style="info")
        elif choice in ("m", "model"):
            await self._execute_model_interactive()
        elif choice in ("s", "system", "prompt"):
            await self._execute_setup_prompt()
        else:
            _print(f"Unknown option: {choice}", style="warn")

    async def _execute_setup_prompt(self) -> None:
        """Change system prompt mode and persist."""
        _print(
            "\nSystem prompt: (d)efault preset / (c)ustom / Enter to cancel",
            style="info",
        )
        choice = await self._input_handler.get_user_input("Choice [d]: ")
        choice = choice.strip().lower()
        if not choice:
            _print("Cancelled.", style="dim")
            return

        if choice in ("c", "custom"):
            text = await self._input_handler.get_user_input("System prompt: ")
            text = text.strip()
            if text:
                save_agent_md(text)
                prompt_mode = "custom"
                self.custom_system_prompt = text
                self._state.custom_system_prompt = text
            else:
                prompt_mode = "default"
                self.custom_system_prompt = None
                self._state.custom_system_prompt = None
        else:
            prompt_mode = "default"
            self.custom_system_prompt = None
            self._state.custom_system_prompt = None

        self.config = IsotopeConfig(
            provider=self.config.provider,
            model=self.config.model,
            preset=self.config.preset,
            system_prompt=prompt_mode,
            debug=self.config.debug,
            sessions_dir=self.config.sessions_dir,
            skills=self.config.skills,
            tools=self.config.tools,
            mcp_servers=self.config.mcp_servers,
        )
        save_config(self.config)
        self._rebuild_agent()
        _print(f"✓ System prompt: {prompt_mode} (saved)", style="info")

    def _execute_show_provider(self) -> None:
        """Show current provider/model/system prompt info."""
        ptype = self.config.provider.type
        label = PROVIDER_LABELS.get(ptype, ptype)
        base_url = self.config.provider.base_url
        _print(f"Provider: {label} ({base_url})", style="info")
        _print(f"Model: {self.model}", style="model")
        sp_mode = self.config.system_prompt
        if sp_mode == "custom":
            prompt_text = load_agent_md()
            preview = (
                (prompt_text[:60] + "...") if len(prompt_text) > 60 else prompt_text
            )
            _print(f"System prompt: custom — {preview}", style="dim")
        elif sp_mode == "default":
            _print(f"System prompt: {self.preset.name} preset default", style="dim")
        else:
            _print("System prompt: not configured", style="dim")

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
            session_id = (
                self.resume_session_id if hasattr(self, "resume_session_id") else None
            )
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
                self._streamed_text = False
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

                (
                    trailing_text,
                    steer_text,
                    partial_msg,
                ) = await self._finish_stream_iteration(
                    gen=gen,
                    buf=buf,
                    done=done,
                    pending=pending,
                    input_task=input_task,
                )

                if steer_text:
                    current_text = self._apply_steering_redirect(
                        steer_text, partial_msg
                    )
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

    async def _run_setup_wizard(self) -> IsotopeConfig:
        """Interactive first-run setup wizard.

        Returns the configured IsotopeConfig (also saves to disk).
        """
        _print(
            "\nWelcome to Isotope! Let's configure your AI provider.\n",
            style="info",
        )

        _cancel = " (Ctrl+D to cancel)"

        # Provider selection
        _print("Choose a provider:", style="info")
        provider_keys = list(PROVIDER_LABELS.keys())
        for i, key in enumerate(provider_keys, 1):
            _print(f"  {i}. {PROVIDER_LABELS[key]}", style="dim")

        choice = await self._input_handler.get_user_input(f"\nProvider [1]{_cancel}: ")
        choice = choice.strip()
        try:
            idx = int(choice) - 1 if choice else 0
            if not (0 <= idx < len(provider_keys)):
                idx = 0
        except ValueError:
            idx = 0
        ptype = provider_keys[idx]
        defaults = PROVIDER_DEFAULTS[ptype]

        # Base URL (only ask for proxy)
        base_url = defaults["base_url"]
        if ptype == "proxy":
            custom_url = await self._input_handler.get_user_input(
                f"Base URL [{base_url}]{_cancel}: "
            )
            if custom_url.strip():
                base_url = custom_url.strip()

        # API key
        api_key = ""
        if ptype != "proxy":
            env_var = defaults.get("env_key", "")
            env_val = os.environ.get(env_var, "") if env_var else ""
            hint = f" (or set {env_var})" if env_var else ""
            if env_val:
                api_key = await self._input_handler.get_user_input(
                    f"API key [from {env_var}]{_cancel}: "
                )
                if not api_key.strip():
                    api_key = env_val
            else:
                api_key = await self._input_handler.get_user_input(
                    f"API key{hint}{_cancel}: "
                )
                api_key = api_key.strip()

        # Model — fetch available models from provider API
        default_model = defaults["default_model"]
        _print("\nFetching available models...", style="dim")
        models = await fetch_available_models(
            base_url, api_key=api_key, provider_type=ptype
        )

        if models:
            # Separate hint entry ("N more — type a model name directly")
            hint_entry = ""
            if models and models[-1].startswith("("):
                hint_entry = models.pop()

            # Place default model first if present
            if default_model in models:
                models.remove(default_model)
                models.insert(0, default_model)

            _print("\nAvailable models:", style="info")
            for i, m in enumerate(models, 1):
                suffix = " (default)" if m == default_model else ""
                _print(f"  {i}. {m}{suffix}", style="dim")
            if hint_entry:
                _print(f"  {hint_entry}", style="dim")

            model_choice = await self._input_handler.get_user_input(
                f"\nModel [1]{_cancel}: "
            )
            model_choice = model_choice.strip()
            try:
                midx = int(model_choice) - 1 if model_choice else 0
                if not (0 <= midx < len(models)):
                    midx = 0
            except ValueError:
                # If they typed a model name directly, use it
                model = model_choice or default_model
                midx = -1
            if midx >= 0:
                model = models[midx]
        else:
            # Fallback: manual input
            model_input = await self._input_handler.get_user_input(
                f"Default model [{default_model}]{_cancel}: "
            )
            model = model_input.strip() or default_model

        # System prompt
        _print(
            "\nCustom system prompt (Enter to use preset default):",
            style="info",
        )
        sys_prompt_input = await self._input_handler.get_user_input(
            f"System prompt{_cancel}: "
        )
        sys_prompt_text = sys_prompt_input.strip()

        if sys_prompt_text:
            prompt_mode = "custom"
            save_agent_md(sys_prompt_text)
        else:
            prompt_mode = "default"

        # Build and save config
        from isotope_agents.config import ProviderConfig

        config = IsotopeConfig(
            provider=ProviderConfig(
                type=ptype,
                base_url=base_url,
                api_key=api_key,
            ),
            model=model,
            system_prompt=prompt_mode,
        )
        save_config(config)
        _print("\n✓ Saved to ~/.isotope/settings.json\n", style="info")
        return config

    async def run(self) -> None:
        """Main TUI loop."""
        from isotope_agents import __version__

        _print(f"isotope-agents TUI v{__version__}", style="info")

        # First-run experience: if no config and no env vars, run wizard
        needs_fre = (
            self.config.provider.type == "proxy"
            and not self.config.provider.api_key
            and self.config.model == "default"
        )
        if needs_fre:
            self.config = await self._run_setup_wizard()

        # Resolve model if not set by CLI
        if not self.model:
            if self.config.model and self.config.model != "default":
                self.model = self.config.model
            else:
                defaults = PROVIDER_DEFAULTS.get(
                    self.config.provider.type, PROVIDER_DEFAULTS["proxy"]
                )
                self.model = defaults["default_model"]

        ptype = self.config.provider.type
        _print(f"Provider: {ptype}", style="dim")
        _print(f"Model: {self.model}", style="model")
        _print(f"Workspace: {WORKSPACE}", style="dim")

        # System prompt resolution based on mode:
        # - "none"    → not yet configured, ask user
        # - "default" → use preset system prompt, skip asking
        # - "custom"  → load from ~/.isotope/agent.md
        sp_mode = self.config.system_prompt
        if sp_mode == "custom":
            agent_md = load_agent_md()
            if agent_md:
                self.custom_system_prompt = agent_md
                _print("System prompt: loaded from ~/.isotope/agent.md", style="dim")
            else:
                _print(
                    f"Using {self.preset.name} preset (agent.md empty)",
                    style="dim",
                )
        elif sp_mode == "default":
            _print(f"Using {self.preset.name} preset system prompt", style="dim")
        else:
            # "none" — not yet configured, ask user
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

        _print(
            "\nType your message (or /help for commands). Ctrl+D to exit.\n",
            style="dim",
        )

        while True:
            try:
                if self._input_handler.has_prompt_toolkit:
                    _print("─" * 50, style="white")
                    line = await self._input_handler.get_user_input(
                        "<style fg='#5599ff'><b>› </b></style>"
                    )
                else:
                    _print_inline("> ", style="user")
                    line = await self._input_handler.get_user_input("")

                if self._input_handler.has_prompt_toolkit:
                    self._input_handler.clear_prefill_text()

            except EOFError:
                # Ctrl+D — exit
                break
            except KeyboardInterrupt:
                # Ctrl+C — clear current input, continue
                self._input_handler.clear_prefill_text()
                continue

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                should_quit = await self._handle_command(line)
                if should_quit:
                    break
                continue

            await self._send_message(line)

        print()
        _print("Bye!", style="info")


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
