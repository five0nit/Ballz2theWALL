# Background command jobs — local dev6 candidate

No additional end-user setup. Existing ON → Start agent flow exposes the new tool
through the already-managed MCP connection; restart an older connected agent after
installing the new local build to refresh its tool inventory.

## Agent contract

Use `machine_exec` with `background:true` for long commands. Account rights are the default:

```json
{
  "argv": ["python", "-u", "build.py"],
  "cwd": "/absolute/path/to/project",
  "background": true,
  "timeout": 0
}
```

`argv` is passed without shell expansion; use a platform-appropriate executable
and explicit working directory. The JSON above is an example, not an execution receipt.
The reply includes a generated `job_id`, `status`, creation time, timeout and current
bounded output. `timeout` defaults to **0** for background commands, **120** for
foreground commands. Zero means no command deadline; positive integer values are
accepted without a fixed upper cap. It does not mean the session lasts forever.

Call `machine_job` in the **same MCP session**:

```json
{"operation": "list"}
```

```json
{"operation": "status", "job_id": "<exact job_id returned by machine_exec>"}
```

```json
{"operation": "cancel", "job_id": "<exact job_id returned by machine_exec>"}
```

- `list`: metadata only for active and retained completed commands.
- `status`: `running`, `cancelling`, `completed`, `failed`, `timed_out` or `cancelled`.
  Running replies include partial stdout/stderr; terminal replies add exit/failure
  details. Failed, timed-out and cancelled final results have MCP `isError:true`.
- `cancel`: request termination, then inspect until terminal status. Repeated cancel
  of a retained terminal job returns its unchanged final result.
- Output keeps the first **256 KiB per stream** and continues draining excess data
  so noisy commands do not deadlock. UTF-8 replacement decoding handles binary
  output. `truncated:true` marks dropped bytes. Write full logs to a task-specific
  file when needed; partial output depends on the child flushing its own buffers.
- Completed history keeps the latest **64** records. Active jobs are not evicted.
  Listing reports how many completed records expired. Expired/unknown handles fail
  explicitly instead of silently starting or substituting another command.
- Start is **not idempotent**: repeating `machine_exec` starts another command.
  Poll the existing handle instead of retrying start after success.

## Ownership and shutdown

Jobs are in-memory, session-owned subprocesses, not services or scheduled tasks.
OFF, activation replacement and orderly MCP disconnect cancel managed parent
commands. A closed/revoked session cannot start new jobs or use old handles.
No cross-session resume, restart persistence, hard-crash cleanup guarantee or
termination guarantee for escaped/detached descendants is implemented.

Add `administrator:true` to use the already-approved Windows helper. Starting a
command never launches UAC or silently falls back to account rights. The helper
must be elevated and bound to the current activation. Each command owns a private
authenticated connection; disconnect cancels its direct child. Four helper job
slots preserve capacity for status and OFF requests. Administrator results include
`administrator:true` and observed `elevated` state; failures never fabricate success.
One-shot `ballz machine tool` cannot own a background job; use the persistent agent
MCP connection. Native owner-approved elevation acceptance remains separate from
scratch tests with injected privilege detection.

This feature avoids holding a single MCP request open for the command duration.
It does not remove the client's request deadline for other tools, prevent the
client terminating its server, alter agent/provider limits or grant OS privileges.

## Historical verification (not dev6 acceptance)

Final **0.3.0a0.dev3** receipt is retained locally at
`docs/verification/command-jobs/acceptance.json`; it is not a public download.

- Source and fresh, outside-repository installed wheel: **824 passed, 4 skipped** each.
- Native Windows installed-wheel command/protocol/lifecycle tests: **74 passed, 1 skipped**.
- Actual 125-second jobs completed under a 120-second MCP per-request timeout on
  both WSL and native Windows; live output and a scratch disk marker verified.
- Windows ZIP clean install and reinstall passed; **21** installed package files
  matched the wheel and source. PATH/shortcut state remained unchanged.
- Two reproduced output-reader startup failure paths now reap the owned child.
  The earlier dev2 candidate and its evidence are preserved separately.
- Scoped current-runtime/test/installer/documentation Gitleaks scan: zero findings.
  This does not claim a fresh scan of git history or unrelated archived evidence.

No new authenticated agent, desktop/browser, elevation or physical Mac acceptance
is claimed. Installer archives remain unsigned, unpublished development builds.


Raw historical evidence stays local under `docs/verification/command-jobs/`;
historical dev1 desktop/browser acceptance remains separately identified in
[CONSUMER-ACCESS.md](CONSUMER-ACCESS.md).
Development leaves real profiles, logins, host OS permissions and public releases
unchanged. Local installer ZIPs remain unsigned; Mac runtime acceptance is pending.

## Current candidate

Dev6 adds approved-helper background jobs, explicit pending-approval recovery and
installer component checks for `admin_jobs.py` and `wire_json.py`. Public evidence:
[sanitized dev6 summary](verification/release-readiness/public-summary.json).
Independent review, clean installed-wheel
and native acceptance results must refer to this candidate's exact bytes; historical
dev3/dev5 results do not certify dev6. Public release remains blocked until its
required gates pass. Firmware/bootloader control is not implemented.
