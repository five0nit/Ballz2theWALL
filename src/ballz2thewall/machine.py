"""Actual local machine tools and an activation-gated native desktop MCP proxy.

No alternate AI runtime. No network listener. Each stdio client owns its Cua
runtime; OFF rejects new calls and closes the managed desktop subprocess.
"""
from __future__ import annotations

import asyncio
import os
import platform
import re
import subprocess
import sys
import threading
import time
from contextlib import AsyncExitStack
from importlib.resources import files
from pathlib import Path

OUTPUT_LIMIT = 262144
REQUEST_LIMIT = 65536


def require_on(state: Path, activation_id: str) -> dict:
    from .onboarding import Activation
    if not isinstance(activation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", activation_id):
        raise ValueError("Invalid machine activation identity")
    record = Activation(state).status()
    if record.get("phase") != "on":
        raise ValueError("Ballz machine access is OFF; turn ON in the owner launcher")
    if record.get("id") != activation_id:
        raise ValueError("This machine client belongs to an older activation; restart the selected agent")
    if record.get("machine_access") is not True:
        raise ValueError("This activation has runtime settings only, not machine access; turn OFF then ON")
    return record


def server_spec(state: Path, activation_id: str) -> dict:
    return {"command": str(Path(sys.executable).absolute()),
            "args": ["-I", "-m", "ballz2thewall", "machine", "serve", "--state-dir",
                     str(state.expanduser().absolute()), "--activation-id", activation_id]}


def desktop_spec() -> dict:
    try:
        binary = files("cua_driver").joinpath("bin", "cua-driver.exe" if os.name == "nt" else "cua-driver")
    except ModuleNotFoundError:
        raise ValueError("Desktop driver missing; reinstall Ballz2theWALL with its machine dependencies") from None
    if not binary.is_file():
        raise ValueError("Native desktop driver is unavailable on this platform")
    # --direct owns the runtime, rather than sharing/stopping the user's daemon.
    # On Mac it deliberately inherits the launching host's TCC identity.
    # 0.28.1 rejects serve-only authorization flags on `mcp`. Direct MCP reads
    # these two supported environment values; existing-profile access is included.
    env = dict(os.environ)
    env.update(CUA_DRIVER_PERMISSION_MODE="unrestricted",
               CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS="1")
    return {"command": str(binary), "args": ["mcp", "--direct", "--no-overlay"], "env": env}


def validate_exec(argv: list[str], cwd: str, timeout: int) -> tuple[list[str], Path, int]:
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 256
            or any(not isinstance(s, str) or "\x00" in s for s in argv)
            or not argv[0] or sum(len(s.encode()) for s in argv) > REQUEST_LIMIT):
        raise ValueError("argv must be a nonempty string array, at most 64 KiB")
    if type(timeout) is not int or timeout < 0:
        raise ValueError("timeout must be a nonnegative integer; 0 means no deadline")
    if not isinstance(cwd, str) or "\x00" in cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError("cwd must be an existing absolute directory")
    return argv, Path(cwd), timeout


class CommandOutput:
    """Bounded, byte-preserving capture shared by foreground and background calls."""

    def __init__(self):
        self._buffers = [bytearray(), bytearray()]
        self._truncated = False
        self._lock = threading.Lock()

    def append(self, index: int, chunk: bytes) -> None:
        with self._lock:
            remaining = OUTPUT_LIMIT - len(self._buffers[index])
            self._buffers[index].extend(chunk[:remaining])
            self._truncated |= len(chunk) > remaining

    def snapshot(self) -> dict:
        with self._lock:
            return {"stdout": self._buffers[0].decode("utf-8", errors="replace"),
                    "stderr": self._buffers[1].decode("utf-8", errors="replace"),
                    "truncated": self._truncated}


def run_command(argv: list[str], cwd: str, timeout: int = 120, *, still_active=None,
                output: CommandOutput | None = None) -> dict:
    argv, directory, timeout = validate_exec(argv, cwd, timeout)
    if still_active is not None:
        still_active()
    output = output if output is not None else CommandOutput()

    def drain(stream, index):
        try:
            # read() can wait for a full buffer. read1() exposes partial lines
            # immediately, including progress bars without trailing newlines.
            while chunk := stream.read1(8192):
                output.append(index, chunk)
        finally:
            stream.close()

    threads = []
    timed_out = cancelled = False
    process = subprocess.Popen(argv, cwd=directory, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    try:
        # Integer nanoseconds preserve every accepted positive integer timeout.
        # Protect all post-spawn initialization, including clock failures.
        deadline = time.monotonic_ns() + timeout * 1_000_000_000 if timeout else None
        for i, stream in enumerate((process.stdout, process.stderr)):
            thread = threading.Thread(target=drain, args=(stream, i), daemon=True)
            threads.append(thread)
            thread.start()
        while process.poll() is None:
            if still_active is not None:
                try:
                    still_active()
                except (ValueError, OSError):
                    cancelled = True
            timed_out = deadline is not None and time.monotonic_ns() >= deadline
            if cancelled or timed_out:
                break
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
    finally:
        # Also reap the child if reader startup or a supervision callback fails.
        # Never leave a successfully spawned process behind a failed job result.
        try:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        finally:
            for i, stream in enumerate((process.stdout, process.stderr)):
                if i < len(threads) and threads[i].ident is not None:
                    threads[i].join(timeout=1)
                else:
                    stream.close()
    # Detached descendants can retain inherited pipes. They are not claimed stopped.
    return {**output.snapshot(), "returncode": process.returncode,
            "timed_out": timed_out, "cancelled": cancelled,
            "descendant_output_open": any(t.is_alive() for t in threads),
            "elevated": False}


def file_operation(operation: str, path: str, text: str = "", overwrite: bool = False) -> dict:
    if not isinstance(path, str) or "\x00" in path or not Path(path).is_absolute():
        raise ValueError("path must be absolute")
    target = Path(path)
    if operation == "read":
        with target.open("rb") as stream:
            raw = stream.read(OUTPUT_LIMIT + 1)
        return {"path": str(target), "text": raw[:OUTPUT_LIMIT].decode("utf-8", errors="replace"),
                "truncated": len(raw) > OUTPUT_LIMIT}
    if operation == "write":
        if not isinstance(text, str) or len(text.encode()) > OUTPUT_LIMIT or type(overwrite) is not bool:
            raise ValueError("text must be at most 256 KiB; overwrite must be boolean")
        if target.exists() and not overwrite:
            raise ValueError("File already exists; explicitly set overwrite=true")
        with target.open("wb" if overwrite else "xb") as stream:
            count = stream.write(text.encode("utf-8"))
        return {"path": str(target), "bytes": count}
    if operation == "list":
        entries = []
        with os.scandir(target) as iterator:
            for item in iterator:
                if len(entries) == 1000:
                    return {"entries": entries, "truncated": True}
                entries.append({"name": item.name, "directory": item.is_dir(follow_symlinks=False),
                                "symlink": item.is_symlink()})
        return {"entries": entries, "truncated": False}
    if operation == "stat":
        stat = target.stat()
        return {"path": str(target), "bytes": stat.st_size, "mode": oct(stat.st_mode),
                "directory": target.is_dir(), "modified_ns": stat.st_mtime_ns}
    raise ValueError("operation must be read, write, list or stat; use machine_exec for other filesystem operations")


def call_local(state: Path, activation_id: str, name: str, args: dict, *, jobs=None) -> dict:
    require_on(state, activation_id)
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")
    if name == "machine_status":
        from .admin import status
        return {"machine_access": "on", "platform": platform.system(), "python": sys.executable,
                "administrator": status(state), "desktop": "native Cua tools; inspect desktop_check_permissions",
                "scope": "current OS account plus separately approved administrative helper",
                "off": "reject new calls and close managed desktop runtime; completed work/OS grants remain"}
    if name == "machine_exec":
        argv, cwd, timeout = validate_exec(args.get("argv"), args.get("cwd"), args.get("timeout", 120))
        administrator = args.get("administrator", False)
        if type(administrator) is not bool:
            raise ValueError("administrator must be boolean")
        background = args.get("background", False)
        if type(background) is not bool:
            raise ValueError("background must be boolean")
        if background:
            if jobs is None:
                raise ValueError("Background commands require a connected MCP session, not a one-shot CLI call")
            jobs.require_owner(state, activation_id)
            return jobs.start(argv, str(cwd), args.get("timeout", 0), administrator=administrator)
        if administrator:
            from .admin import execute
            return execute(state, argv, str(cwd), timeout)
        return run_command(argv, str(cwd), timeout, still_active=lambda: require_on(state, activation_id))
    if name == "machine_file":
        return file_operation(args.get("operation"), args.get("path"), args.get("text", ""), args.get("overwrite", False))
    if name == "machine_job":
        if jobs is None:
            raise ValueError("Command jobs require the original connected MCP session")
        jobs.require_owner(state, activation_id)
        return jobs.control(args.get("operation"), args.get("job_id"))
    raise ValueError("Unknown machine tool")


def local_tools():
    from mcp.types import Tool
    return [
        Tool(name="machine_status", description="Read actual machine connection and separately approved administrator-helper status.",
             inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
        Tool(name="machine_exec", description="Run an OS command with captured output. For long commands use background=true, then machine_job status/cancel with the returned job_id; start returns promptly rather than waiting through the MCP client timeout. Background defaults to no command deadline and lasts only while this MCP session is connected and ON. Administrator execution supports foreground and background after owner approval; helper EOF cancels its direct child. No shell expansion: pass the shell as argv[0] if needed.",
             inputSchema={"type": "object", "required": ["argv", "cwd"], "additionalProperties": False,
                "properties": {"argv": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 256},
                    "cwd": {"type": "string"}, "timeout": {"type": "integer", "minimum": 0, "description": "Seconds; 0 runs until completion or OFF."},
                    "administrator": {"type": "boolean", "default": False},
                    "background": {"type": "boolean", "default": False}}}),
        Tool(name="machine_file", description="Read/write UTF-8 files, list folders or stat any path accessible to the OS account. Output capped at 256 KiB; use machine_exec for binary files, large data, copy/move/delete or administration.",
             inputSchema={"type": "object", "required": ["operation", "path"], "additionalProperties": False,
                "properties": {"operation": {"type": "string", "enum": ["read", "write", "list", "stat"]},
                    "path": {"type": "string"}, "text": {"type": "string"}, "overwrite": {"type": "boolean", "default": False}}}),
        Tool(name="machine_job", description="Inspect or cancel this MCP session's background commands. Status includes live bounded stdout/stderr and final exit details. Cancel requests termination; poll until terminal status. List omits output; latest 64 completed records retained. OFF/disconnect cancels managed commands. No restart persistence or escaped-descendant guarantee.",
             inputSchema={"type": "object", "required": ["operation"], "additionalProperties": False,
                "properties": {"operation": {"type": "string", "enum": ["list", "status", "cancel"]},
                    "job_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}},
                "allOf": [{"if": {"properties": {"operation": {"enum": ["status", "cancel"]}}},
                           "then": {"required": ["job_id"]},
                           "else": {"not": {"required": ["job_id"]}}}]}),
    ]


async def _watch_off(state: Path, activation_id: str) -> None:
    while True:
        await asyncio.sleep(0.3)
        try:
            require_on(state, activation_id)
        except (ValueError, OSError):
            return


async def serve(state: Path, activation_id: str, *, desktop: bool = True) -> None:
    """Serve stdio until client exit or OFF; never open a network endpoint."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent

    from .admin import AdminError
    from .machine_jobs import CommandJobs

    require_on(state, activation_id)
    server = Server("Ballz2theWALL-machine")
    async with AsyncExitStack() as stack:
        jobs = CommandJobs(state, activation_id)
        stack.push_async_callback(asyncio.to_thread, jobs.close)
        upstream = None
        native_tools = []
        if desktop:
            spec = desktop_spec()
            # Preserve desktop-session variables; never substitute another user/home.
            transport = await stack.enter_async_context(stdio_client(StdioServerParameters(**spec)))
            upstream = await stack.enter_async_context(ClientSession(*transport))
            await asyncio.wait_for(upstream.initialize(), timeout=30)
            native_tools = (await asyncio.wait_for(upstream.list_tools(), timeout=30)).tools
        mapping = {"desktop_" + item.name: item.name for item in native_tools}
        tools = [*local_tools(), *(item.model_copy(update={"name": "desktop_" + item.name}) for item in native_tools)]

        @server.list_tools()
        async def list_tools():
            require_on(state, activation_id)
            return tools

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            try:
                require_on(state, activation_id)
                if name in mapping and upstream is not None:
                    return await upstream.call_tool(mapping[name], arguments)
                result = await asyncio.to_thread(call_local, state, activation_id, name, arguments, jobs=jobs)
                failed = bool(result.get("error") or result.get("timed_out") or result.get("cancelled") or result.get("revoked")
                              or result.get("returncode", 0) != 0)
                from .wire_json import dumps
                return CallToolResult(isError=failed, content=[TextContent(type="text", text=dumps(result, max_bytes=8 * 1024 * 1024))])
            except (ValueError, AdminError, OSError, subprocess.SubprocessError) as exc:
                # No old config/credential values in diagnostics.
                message = str(exc) if isinstance(exc, (ValueError, AdminError)) else "Machine operation failed; inspect path, executable and OS access"
                return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])

        async with stdio_server() as streams:
            serving = asyncio.create_task(server.run(*streams, server.create_initialization_options()))
            watching = asyncio.create_task(_watch_off(state, activation_id))
            try:
                await asyncio.wait((serving, watching), return_when=asyncio.FIRST_COMPLETED)
                if serving.done():
                    await serving
            finally:
                serving.cancel()
                watching.cancel()
                await asyncio.gather(serving, watching, return_exceptions=True)


async def driver_call(state: Path, activation_id: str, tool: str | None, arguments: dict):
    """Direct CLI route to one owned desktop runtime; all adapters also use MCP."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    require_on(state, activation_id)
    spec = desktop_spec()

    async def operation():
        # Own and unwind MCP/AnyIO contexts in the same task. Watching includes
        # connection, initialization and discovery, not only the final call.
        async with stdio_client(StdioServerParameters(**spec)) as transport:
            async with ClientSession(*transport) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                require_on(state, activation_id)
                if tool is None:
                    return (await session.list_tools()).model_dump(mode="json")
                return (await session.call_tool(tool.removeprefix("desktop_"), arguments)).model_dump(mode="json")

    running = asyncio.create_task(operation())
    watching = asyncio.create_task(_watch_off(state, activation_id))
    try:
        await asyncio.wait((running, watching), return_when=asyncio.FIRST_COMPLETED)
        require_on(state, activation_id)
        if watching.done():
            # A transient OFF observation must not be undone by a later read.
            raise ValueError("Ballz machine access was revoked during the desktop operation")
        return await running
    finally:
        running.cancel()
        watching.cancel()
        await asyncio.gather(running, watching, return_exceptions=True)
