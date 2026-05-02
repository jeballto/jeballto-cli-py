# jeballto-cli

CLI for the Jeballto VM Agent API. It lets you manage macOS virtual machines, images, and blueprint-style executions from the terminal.

> [!IMPORTANT]
> Jeballto and this CLI are currently in public beta. Some functionality may be incomplete, unstable, or change in breaking ways before a stable release. Pin versions for critical workflows and review release notes before upgrading.

## Version

This README reflects CLI/API changes through `1.0.0-beta.1`.

### What's new since 0.3.1

- **Ephemeral VMs + TTL** - `vm create` / `vm clone` accept `--ephemeral` and `vm create --lifetime <seconds>` for auto-delete VMs with an optional max lifetime.
- **`vm update`** - new PATCH command to rename a VM or change CPU/memory/disk (disk is grow-only; resource changes require the VM stopped).
- **`auth verify`** - new command that validates the configured bearer token against the agent.
- **`config set`** - new flags `--timezone`, `--vnc-port-range-start`, `--vnc-port-range-end`.
- **Resources schema** - `memorySize` / `diskSize` are now human-readable strings (e.g. `"8GB"`), replacing the legacy `memoryGB` / `diskGB` numbers.
- **Push safety** - pushing an image requires the VM to be stopped; a registry reachability check runs before compression.

## Installation

```bash
pip install jeballto-cli
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv pip install jeballto-cli
```

Requires Python `3.14+`.

## Quick Start

```bash
# Check agent connectivity
jeballto health

# Create and start a VM
jeballto vm create my-vm --cpu 4 --memory 8GB --disk 64GB
jeballto vm start <vm-id>

# Install macOS (latest from Apple)
jeballto vm install start <vm-id>

# Or install from a specific source (HTTPS, file://, or absolute path)
jeballto vm install start <vm-id> --source https://example.com/macos.ipsw

# Execute a command in the guest
jeballto vm execute <vm-id> "uname -a"

# Pull, list, and push OCI images
jeballto image pull registry.example.com/macos:latest
jeballto image list --limit 20 --offset 0
jeballto image push registry.example.com/macos:backup --vm <vm-id>
```

## Configuration Resolution

Settings are resolved in this order (first match wins):

1. CLI flags (`--base-url`, `--token`, `--output`, etc.)
2. Environment variables (`JEBALLTO_BASE_URL`, `JEBALLTO_TOKEN`, etc.)
3. Config file (`~/.config/jeballto-cli/config.toml`)
4. Jeballto Agent config (`~/Library/Application Support/Jeballto/config.json`)
5. Built-in defaults (`http://localhost:8011/v1`, `120s`, table output)

### Config File Example

```toml
[client]
base_url = "http://localhost:8011/v1"
token = "your-token-here"
timeout = 60
insecure = false
output = "table"
```

### Environment Variables

| Variable | Description |
|---|---|
| `JEBALLTO_BASE_URL` | Agent base URL |
| `JEBALLTO_TOKEN` | Bearer token |
| `JEBALLTO_TIMEOUT` | Request timeout in seconds |
| `JEBALLTO_INSECURE` | Disable TLS verification |
| `JEBALLTO_OUTPUT` | Default output format (`table`, `json`, `yaml`) |

## Global CLI Options

```text
--base-url, -u    Jeballto agent base URL
--token, -t       Bearer token
--output, -o      Output format: json, yaml, table
--timeout         Request timeout in seconds
--insecure, -k    Disable TLS verification
--config, -c      Path to config file
--version         Show version
```

## Command Reference

### `vm` - Virtual Machines

| Command | Description |
|---|---|
| `vm create NAME` | Create VM (`--cpu`, `--memory`, `--disk`, `--image`, `--ephemeral`, `--lifetime`) |
| `vm update VM_ID` | Update VM name/resources (`--name`, `--cpu`, `--memory`, `--disk`) - PATCH |
| `vm list` | List VMs (`--limit`, `--offset`) |
| `vm get VM_ID` | Get VM details |
| `vm delete VM_ID` | Delete VM (`--force`, `--yes`) |
| `vm wipe` | Delete all VMs (`--yes`) |
| `vm start VM_ID` | Start VM (`--wait`) |
| `vm stop VM_ID` | Stop VM (`--wait`) |
| `vm pause VM_ID` | Pause VM |
| `vm resume VM_ID` | Resume VM |
| `vm clone VM_ID` | Clone VM (`--name`, `--cpu`, `--memory`, `--disk`, `--force`, `--ephemeral`) |
| `vm execute VM_ID COMMAND` | Run command via SSH (`--user`, `--password`, `--timeout`) |
| `vm keystrokes VM_ID KEY...` | Inject keystrokes |
| `vm state VM_ID` | Get VM state |
| `vm events VM_ID` | Get VM events (`--limit`) |

### `vm install`, `vm ssh`, `vm vnc`, `vm gui`

| Command | Description |
|---|---|
| `vm install start VM_ID` | Start macOS install (`--source`, `--wait`) |
| `vm install status VM_ID` | Get install status (`--watch`) |
| `vm ssh info VM_ID` | Get SSH forwarding info |
| `vm ssh enable VM_ID` | Enable SSH forwarding |
| `vm ssh disable VM_ID` | Disable SSH forwarding |
| `vm vnc info VM_ID` | Get VNC forwarding info |
| `vm vnc enable VM_ID` | Enable VNC forwarding |
| `vm vnc disable VM_ID` | Disable VNC forwarding |
| `vm gui open VM_ID` | Open GUI window |
| `vm gui close VM_ID` | Close GUI window |
| `vm gui status VM_ID` | Get GUI status |
| `vm gui screenshot VM_ID` | Save screenshot (`--output-file`) |

### `image` - OCI Images

| Command | Description |
|---|---|
| `image list` | List images (`--limit`, `--offset`) |
| `image get IMAGE_ID` | Get image details |
| `image delete IMAGE_ID` | Delete image (`--yes`) |
| `image wipe` | Delete all images (`--yes`) |
| `image pull REFERENCE` | Pull image (`--timeout`) |
| `image push REFERENCE` | Push image (`--vm` or `--image`, `--timeout`) |

`image push` expects exactly one source:

- VM source: `--vm <vm-id>` -> request source format `vm:<uuid>`
- Image source: `--image <image-id>` -> request source format `image:<uuid>`

### `jeballtofile` - Blueprint Execution

Use JSON steps to create a VM and run a sequence asynchronously.

```bash
jeballto jeballtofile run my-vm \
  --steps '[{"type":"start"},{"type":"execute","command":"echo hello"}]'
```

You can also pass a Jeballtofile from disk:

```bash
# JSON file
jeballto jeballtofile run --file ./Jeballtofile.json

# YAML file
jeballto jeballtofile run --file ./Jeballtofile.yaml
```

`--steps` and `--file` are mutually exclusive.

| Command | Description |
|---|---|
| `jeballtofile run [NAME]` | Start execution (`--steps` or `--file`, `--source`, `--cpu`, `--memory`, `--disk`, `--wait`) |
| `jeballtofile list` | List active/recent executions |
| `jeballtofile get EXECUTION_ID` | Get status and step results |
| `jeballtofile cancel EXECUTION_ID` | Request cancellation |
| `jeballtofile delete EXECUTION_ID` | Delete completed/failed/cancelled execution (`--yes`) |

### `system` - System Operations

| Command | Description |
|---|---|
| `system reset soft` | Delete VMs, images, IPSW cache (keeps config/logs) |
| `system reset hard` | Delete all agent data; process will terminate |

Both reset modes require confirmation (interactive prompt or `--yes`).

### `registry`, `config`, and `auth`

| Command | Description |
|---|---|
| `registry login REGISTRY` | Authenticate (`--username`, `--password`) |
| `registry logout REGISTRY` | Remove registry credentials |
| `config get` | Read runtime config |
| `config set` | Update runtime config (`--json`, `--log-level`, `--timezone`, `--vnc-port-range-start`, `--vnc-port-range-end`) |
| `auth verify` | Verify the configured bearer token against the agent |

## Aliases

Supported aliases:

- `vm ls`, `vm show`, `vm rm`, `vm exec`
- `image ls`, `image show`, `image rm`
- `jeballtofile ls`

## Output Formats

```bash
# Table (default)
jeballto vm list

# JSON
jeballto --output json vm list

# YAML
jeballto --output yaml vm list
```

## Development

```bash
# Clone
# git clone https://github.com/jeballto/jeballto-cli-py.git
cd jeballto-cli-py

# Install dependencies
uv sync --dev

# CLI help
uv run jeballto --help

# Lint + format
uv run ruff check src tests
uv run ruff format src tests

# Type-check
uv run mypy

# Test
uv run pytest
```

## License

See [LICENSE](LICENSE).
