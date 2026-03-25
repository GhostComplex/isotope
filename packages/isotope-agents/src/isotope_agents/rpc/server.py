"""RPC server — reads JSONL commands from stdin, emits events to stdout.

The server wraps an :class:`IsotopeAgent` and exposes it over a
stdin/stdout JSONL protocol, translating between isotope-core
:class:`AgentEvent` instances and the RPC event types defined in
:mod:`isotope_agents.rpc.protocol`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from typing import IO, Any

from isotope_core.types import (
    AgentEndEvent,
    AgentStartEvent,
    MessageUpdateEvent,
    ToolEndEvent,
    ToolStartEvent,
)

from isotope_agents.agent import IsotopeAgent
from isotope_agents.rpc.protocol import (
    AbortCommand,
    AgentEndRpcEvent,
    AgentStartRpcEvent,
    CompactCommand,
    ErrorRpcEvent,
    FollowUpCommand,
    GetStateCommand,
    NewSessionCommand,
    PromptCommand,
    RpcEvent,
    SetModelCommand,
    StateRpcEvent,
    SteerCommand,
    TextDeltaRpcEvent,
    ToolCallEndRpcEvent,
    ToolCallStartRpcEvent,
    parse_command,
)

logger = logging.getLogger(__name__)


class RpcServer:
    """JSONL-over-stdio RPC server for an :class:`IsotopeAgent`.

    Commands arrive on *input_stream* (one JSON object per line).  Events are
    written to *output_stream* in the same format.  The server is fully
    asynchronous — call :meth:`run` inside an ``asyncio`` event loop.

    Example::

        server = RpcServer(agent)
        asyncio.run(server.run())
    """

    def __init__(
        self,
        agent: IsotopeAgent,
        *,
        input_stream: IO[str] | None = None,
        output_stream: IO[str] | None = None,
    ) -> None:
        self.agent = agent
        self._input: IO[str] = input_stream or sys.stdin
        self._output: IO[str] = output_stream or sys.stdout
        self._running = False
        self._current_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main loop: read commands from stdin, dispatch, emit events."""
        self._running = True
        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read a line from stdin in a non-blocking way
                line = await loop.run_in_executor(None, self._input.readline)
            except (OSError, ValueError):
                # Stream closed or invalid
                break

            if not line:
                # EOF
                break

            line = line.strip()
            if not line:
                continue

            await self._dispatch(line)

    def stop(self) -> None:
        """Signal the run loop to stop after the current iteration."""
        self._running = False

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, line: str) -> None:
        """Parse a JSONL line and route to the appropriate handler."""
        try:
            cmd = parse_command(line)
        except ValueError as exc:
            # Try to extract command_id from the raw JSON for error reporting
            command_id = _extract_id(line)
            self._emit(ErrorRpcEvent(message=str(exc), command_id=command_id))
            return

        handlers: dict[str, Any] = {
            "prompt": self._handle_prompt,
            "steer": self._handle_steer,
            "follow_up": self._handle_follow_up,
            "abort": self._handle_abort,
            "get_state": self._handle_get_state,
            "set_model": self._handle_set_model,
            "compact": self._handle_compact,
            "new_session": self._handle_new_session,
        }

        handler = handlers.get(cmd.type)
        if handler is None:
            self._emit(
                ErrorRpcEvent(
                    message=f"No handler for command type: {cmd.type!r}",
                    command_id=cmd.id,
                )
            )
            return

        try:
            await handler(cmd)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error handling command %s", cmd.type)
            self._emit(
                ErrorRpcEvent(
                    message=f"Error handling {cmd.type}: {exc}",
                    command_id=cmd.id,
                )
            )

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def _handle_prompt(self, cmd: PromptCommand) -> None:
        """Run the agent with a user prompt, streaming events to stdout."""
        stream_id = cmd.id or str(uuid.uuid4())[:8]

        self._emit(AgentStartRpcEvent(stream_id=stream_id))

        usage: dict[str, object] = {}

        async for event in self.agent.run(cmd.content):
            if isinstance(event, AgentStartEvent):
                # Already emitted our own AgentStartRpcEvent above
                pass
            elif isinstance(event, MessageUpdateEvent):
                if event.delta:
                    self._emit(
                        TextDeltaRpcEvent(
                            content=event.delta,
                            stream_id=stream_id,
                        )
                    )
            elif isinstance(event, ToolStartEvent):
                self._emit(
                    ToolCallStartRpcEvent(
                        name=event.tool_name,
                        arguments=event.args,
                        stream_id=stream_id,
                    )
                )
            elif isinstance(event, ToolEndEvent):
                self._emit(
                    ToolCallEndRpcEvent(
                        name=event.tool_name,
                        output=str(event.result),
                        is_error=event.is_error,
                        stream_id=stream_id,
                    )
                )
            elif isinstance(event, AgentEndEvent):
                # Capture final usage information if available
                pass

        self._emit(AgentEndRpcEvent(usage=usage, stream_id=stream_id))

    async def _handle_steer(self, cmd: SteerCommand) -> None:
        """Inject a steering instruction into the current turn."""
        await self.agent.steer(cmd.content)
        logger.info("Steering message injected: %.50s…", cmd.content)

    async def _handle_follow_up(self, cmd: FollowUpCommand) -> None:
        """Queue a follow-up message for the next turn."""
        await self.agent.follow_up(cmd.content)
        logger.info("Follow-up queued: %.50s…", cmd.content)

    async def _handle_abort(self, cmd: AbortCommand) -> None:
        """Abort the currently running agent turn."""
        self.agent.abort()
        logger.info("Abort requested")

    async def _handle_get_state(self, cmd: GetStateCommand) -> None:
        """Emit the current agent state."""
        self._emit(
            StateRpcEvent(
                model=self.agent._model or "unknown",
                preset=self.agent.preset.name,
                session_id=self.agent.session_id or "",
                stream_id=cmd.id,
            )
        )

    async def _handle_set_model(self, cmd: SetModelCommand) -> None:
        """Update the model used by the agent."""
        # For now, log the model change.  Full model-swap requires
        # re-initialising the provider, which is deferred to a future milestone.
        logger.info("set_model requested: %s (logged, not yet applied)", cmd.model)

    async def _handle_compact(self, cmd: CompactCommand) -> None:
        """Trigger context compaction."""
        result = await self.agent.compact()
        logger.info(
            "Compaction complete: %d messages compacted, %d→%d tokens",
            result.messages_compacted,
            result.tokens_before,
            result.tokens_after,
        )

    async def _handle_new_session(self, cmd: NewSessionCommand) -> None:
        """Create a new session, clearing all context."""
        # Reset the core agent's message history
        self.agent.core.replace_messages([])
        logger.info("New session started — message history cleared")

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(self, event: RpcEvent) -> None:
        """Write a JSONL event to the output stream."""
        self._output.write(event.model_dump_json() + "\n")
        self._output.flush()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_id(line: str) -> str | None:
    """Best-effort extraction of ``id`` from a raw JSON line."""
    try:
        data = json.loads(line)
        if isinstance(data, dict):
            return data.get("id")
    except (json.JSONDecodeError, TypeError):
        pass
    return None
