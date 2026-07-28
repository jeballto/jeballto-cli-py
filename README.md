# jeballto-cli

`jeballto` is the command-line client for the Jeballto VM Agent. It manages
macOS virtual machines, OCI images, registry credentials, agent settings, and
Jeballtofile automation from a terminal or CI job.

The default output is concise and readable. Structured output is stable for
scripts, progress stays on stderr, and actionable failures do not print a Python
traceback unless `--debug` is enabled.

> [!IMPORTANT]
> Jeballto and this CLI are currently in public beta. Pin versions in critical
> workflows and review release notes before upgrading.

## Requirements

- Apple Silicon Mac
- macOS 26.0+
- Python 3.11+
- Running Jeballto VM Agent

Some automation examples use optional `jq` to extract values from JSON output.

## Installation

Install the CLI from a local checkout with `uv`:

```bash
git clone https://github.com/jeballto/jeballto-cli-py.git
cd jeballto-cli-py
uv tool install .
jeballto --version
```

For development, run it directly in the project environment:

```bash
uv sync --dev
uv run jeballto --help
```

## First Run

Copy the API token from the Jeballto menu-bar app, then run:

```bash
jeballto auth login
jeballto doctor
jeballto vm list
```

`auth login` prompts without displaying the token, verifies it against the
selected agent, and stores it in the macOS Keychain. The saved credential is
scoped to the agent base URL. Tokens are never stored in the CLI config file.

Use these commands to inspect or remove the saved credential:

```bash
jeballto auth status
jeballto auth logout
```

For a remote or non-default agent, select the URL before logging in:

```bash
jeballto --base-url https://agent.example.com/v1 auth login
```

## Quick Start

Create a VM, install macOS, start it, and run a command:

```bash
jeballto vm create dev --cpu 4 --memory 8GB --disk 64GB
jeballto vm install start dev
jeballto vm start dev
jeballto vm exec dev -- sw_vers
```

Installation waits and displays progress by default. A local IPSW path or HTTPS
URL can be supplied explicitly:

```bash
jeballto vm install start dev --ipsw /path/to/macos.ipsw
```

Inspect the VM, capture a screenshot, then clean up:

```bash
jeballto vm get dev
jeballto vm screenshot dev --output-file dev.png
jeballto vm stop dev
jeballto vm delete dev --yes
```

Commands that select an existing VM accept a VM name or ID. Commands that select
an existing local image accept an OCI reference or image ID. An ambiguous name
or reference produces a clear error with the matching IDs.

## Long-Running Operations

The CLI waits by default for operations where the result matters:

- `vm install start`
- `image pull`
- `image push`
- `run submit`
- `run cancel`

Use `--detach` to return after submission. The response includes the operation
or execution ID needed to inspect it later.

```bash
OPERATION_ID=$(jeballto --output json image pull \
  registry.example.com/macos:latest --detach | jq -r '.operationId')
jeballto image operation list --active
jeballto image operation wait "$OPERATION_ID"

RUN_ID=$(jeballto --output json run submit \
  --file ./Jeballtofile.yaml --detach | jq -r '.id')
jeballto run wait "$RUN_ID"

jeballto vm install start dev --detach
jeballto vm install status dev --watch
```

`--timeout` on an image transfer is the agent-side transfer budget.
`--wait-timeout` only limits how long the CLI watches an operation. Reaching a
watch timeout does not cancel work on the agent.

Pressing Ctrl-C while watching exits with status 130 and leaves the remote
operation running. The CLI prints the command that can resume observation.

## VM Workflows

### Create From an OCI Image

```bash
jeballto image pull registry.example.com/macos:latest
jeballto vm create ci --image registry.example.com/macos:latest --ephemeral
jeballto vm start ci
```

Custom CPU, memory, and disk values are applied after image-based creation when
they are provided.

### Ephemeral VMs

```bash
jeballto vm create job --image registry.example.com/macos:latest --ephemeral
jeballto vm create short-lived \
  --cpu 4 --memory 8GB --disk 64GB \
  --ephemeral --lifetime 3600
```

`--lifetime` counts running seconds. An ephemeral VM is deleted after it
finishes or fails.

Clone settings can be adjusted at creation time:

```bash
jeballto vm clone dev --name dev-copy --ephemeral --lifetime 3600
```

### Execute Commands

Pass the command and its arguments after the VM reference. Use `--` before a
guest command that contains options:

```bash
jeballto vm exec dev -- uname -a
jeballto vm exec dev -- softwareupdate --list
jeballto vm exec dev -- sh -lc 'echo "$HOME" && pwd'
```

Use `sh -lc` when the guest command needs shell expansion, pipes, redirection,
or operators such as `&&`.

Human output writes guest stdout directly to stdout and guest stderr directly
to stderr. The CLI exits with the guest process exit code. JSON and YAML include
the full execution response, including truncation flags and `exitCode`.

For SSH credentials, prefer `JEBALLTO_SSH_PASSWORD` or `--password-stdin` over a
command-line password:

```bash
printf '%s\n' "$SSH_PASSWORD" | \
  jeballto vm exec --password-stdin dev -- whoami
```

### Events and GUI Access

```bash
jeballto vm events dev --limit 50
jeballto --output jsonl vm events dev --watch

jeballto vm gui open dev
jeballto vm vnc enable dev
jeballto vm ssh info dev
```

Streaming VM events support human output and JSON Lines.

## Image and Registry Workflows

Sign in without placing a registry password or token in shell history:

```bash
printf '%s\n' "$REGISTRY_TOKEN" | \
  jeballto registry login ghcr.io --username "$REGISTRY_USER" --password-stdin
```

Pull an image, then push a VM or another local image:

```bash
jeballto image pull ghcr.io/example/macos:latest
jeballto image push ghcr.io/example/macos:backup --vm dev
jeballto image push ghcr.io/example/macos:copy \
  --image ghcr.io/example/macos:latest
```

Exactly one of `--vm` or `--image` is required by `image push`.

Background transfer commands live under `image operation`:

```bash
jeballto image operation list
jeballto image operation list --type pull --active
jeballto image operation get "$OPERATION_ID"
jeballto image operation wait "$OPERATION_ID" --type pull
jeballto image operation cancel "$OPERATION_ID"
jeballto image operation cancel --all --type pull --yes
```

## Jeballtofile Automation

Submit a blueprint from YAML or JSON:

```bash
jeballto run submit --file ./Jeballtofile.yaml
```

Submit inline steps:

```bash
jeballto run submit dev \
  --steps '[{"type":"start"},{"type":"execute","command":"echo hello"}]'
```

The `run` hierarchy keeps submission and observation separate:

```bash
jeballto run list
jeballto run get "$RUN_ID"
jeballto run wait "$RUN_ID"
jeballto run cancel "$RUN_ID"
jeballto run delete "$RUN_ID" --yes
```

Cancellation is cooperative. The agent marks the run and its active step as
cancelled, then asks active work to unwind. The CLI waits for the terminal
status by default.

## Agent Configuration

Inspect or update runtime settings:

```bash
jeballto config get

jeballto config set --log-level debug --retention-days 14
jeballto config set --timezone UTC
jeballto config set --system-timezone

jeballto config set --ssh-start 2222 --ssh-end 2223
jeballto config set --vnc-start 5901 --vnc-end 5902
jeballto config set --ssh-forwarding

jeballto config set --registry registry.example.com
jeballto config set --clear-default-registry
jeballto config set --insecure-registry registry.local
jeballto config set --clear-insecure-registries
jeballto config set --blob-transfers 16 --compressions 4
```

Repeating `--insecure-registry` builds the complete replacement list. It does
not append to the currently configured list. Networking changes take effect
after the Jeballto Agent restarts.

Advanced callers can send a partial API config object:

```bash
jeballto config set --json \
  '{"images":{"maxParallelImageBlobTransfers":8}}'
```

## CLI Configuration

Settings resolve in this order:

1. Global command-line flags
2. Environment variables
3. `~/.config/jeballto-cli/config.toml`
4. Local Jeballto Agent config at `~/Library/Application Support/Jeballto/config.json`
5. Built-in defaults

The local agent config is used only to discover its host and port when no base
URL was selected earlier. A URL without a scheme receives `http://`, and a URL
without a path receives `/v1`.

Minimal CLI config:

```toml
[client]
base_url = "http://localhost:8011/v1"
output = "human"
details = false
insecure = false
```

Unknown `[client]` fields are rejected so misspellings do not fail silently. If
an older config contains `client.token`, remove it and run `jeballto auth login`
to migrate the credential to the macOS Keychain.

An optional request timeout applies to each API request:

```toml
[client]
request_timeout = 30
```

Omitting `request_timeout` leaves requests unbounded apart from operation-level
timeouts. The HTTP connection phase still has its own safety limit.

Available environment variables:

| Variable | Purpose |
|---|---|
| `JEBALLTO_BASE_URL` | Agent API base URL |
| `JEBALLTO_TOKEN` | API token for the current process |
| `JEBALLTO_REQUEST_TIMEOUT` | Per-request timeout in seconds |
| `JEBALLTO_INSECURE` | Disable TLS certificate verification |
| `JEBALLTO_OUTPUT` | `human`, `json`, `jsonl`, or `yaml` |
| `JEBALLTO_DETAILS` | Include all fields in human output |
| `JEBALLTO_AGENT_CONFIG` | Alternate local Agent config path |
| `JEBALLTO_SSH_PASSWORD` | Password for `vm exec` |
| `JEBALLTO_REGISTRY_PASSWORD` | Password or token for `registry login` |

The token precedence is `--token`, `JEBALLTO_TOKEN`, then the macOS Keychain.

## Output Contract

Select a format with the global `--output` or `-o` option:

```bash
jeballto vm list
jeballto --output json vm list
jeballto --output yaml vm get dev
jeballto --output jsonl vm events dev --watch
```

| Format | Intended use |
|---|---|
| `human` | Concise, colored terminal output. This is the default. |
| `json` | One formatted JSON document for scripts and API inspection. |
| `jsonl` | One compact JSON value per line, especially for streams. |
| `yaml` | One YAML document for readable structured output. |

Successful command results are written to stdout. Progress, prompts, warnings,
recovery hints, and errors are written to stderr. This makes stdout safe to
pipe into tools such as `jq` without hiding useful progress from an operator.

Use `--details` to include less common API fields in human output. Structured
formats preserve the complete response regardless of this setting.

## Automation and Exit Codes

Use `--no-input` to guarantee that a command never prompts. It does not approve
destructive actions. Add the command-specific `--yes` or `-y` explicitly when
the action is intentional.

```bash
vm_id=$(jeballto --output json vm create ci \
  --cpu 4 --memory 8GB --disk 64GB | jq -r '.id')

jeballto --no-input --output json vm delete "$vm_id" --yes
```

For non-interactive authentication, pass the token through the environment so
it is verified and saved without a prompt:

```bash
JEBALLTO_TOKEN="$TOKEN" jeballto --no-input auth login
```

Common exit statuses:

| Status | Meaning |
|---|---|
| `0` | Command completed successfully. |
| `1` | API failure, local validation failure, failed terminal state, or partial bulk failure. |
| `2` | Invalid command syntax or options. |
| `130` | The user interrupted a watch or long-running command with Ctrl-C. |
| guest code | `vm exec` returns the guest process exit code from 0 through 255. |

`doctor` and `auth status` return 1 when the agent is not ready or authentication
is not valid. Wipe and reset commands also return 1 if only part of the requested
work succeeded.

Machine-readable errors are emitted on stderr in the selected structured format.
Use `--debug` only when diagnosing a CLI defect that requires a Python traceback.

## Command Map

| Command | Purpose |
|---|---|
| `health` | Check whether the agent is reachable. |
| `doctor` | Diagnose URL, connection, authentication, and virtualization. |
| `auth login/status/logout` | Manage and verify the API token in Keychain. |
| `vm` | Create, inspect, clone, update, and control VMs. |
| `vm install` | Start or observe macOS installation. |
| `vm ssh`, `vm vnc`, `vm gui` | Manage remote and local VM access. |
| `image` | Inspect local images and start pull or push transfers. |
| `image operation` | List, inspect, wait for, or cancel transfers. |
| `registry` | Sign in to or out of OCI registries. |
| `config` | Read or update Agent runtime settings. |
| `run` | Submit and manage Jeballtofile runs. |
| `system capabilities` | Inspect host and feature availability. |
| `system reset` | Delete local Agent state with explicit confirmation. |

Run `jeballto <command> --help` at any level for the complete argument and option
reference.

## Development

```bash
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

## License

This project is licensed under the Mozilla Public License 2.0. See
[LICENSE](LICENSE).
