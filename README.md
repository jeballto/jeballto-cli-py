# jeballto-cli

Command-line client for the Jeballto VM Agent API.

Use it to manage macOS VMs, OCI VM images, registry credentials, agent config, and Jeballtofile executions from a terminal.

> [!IMPORTANT]
> Jeballto and this CLI are currently in public beta. Some functionality may be incomplete, unstable, or change in breaking ways before a stable release. Pin versions for critical workflows and review release notes before upgrading.

## Requirements

- Python 3.14+
- Running Jeballto VM Agent
- Apple Silicon Mac with macOS 26.0+ for VM operations

## Installation

Run from source:

```bash
git clone https://github.com/jeballto/jeballto-cli-py.git
cd jeballto-cli-py
uv run jeballto --help
uv run jeballto health
```

## Configuration

Settings resolve in this order:

1. CLI flags
2. Environment variables
3. `~/.config/jeballto-cli/config.toml`
4. Jeballto Agent config at `~/Library/Application Support/Jeballto/config.json`
5. Built-in defaults

Minimal config:

```toml
[client]
base_url = "http://localhost:8011/v1"
token = "your-token-here"
output = "table"
```

Optional client timeout:

```toml
[client]
timeout = 3600
```

Unset timeout means no client-side request timeout. Operation-specific flags such as `image pull --timeout 3600` are still sent to the API and also bound the HTTP request with a small response cushion.

Useful environment variables:

| Variable | Description |
|---|---|
| `JEBALLTO_BASE_URL` | Agent API base URL |
| `JEBALLTO_TOKEN` | Bearer token |
| `JEBALLTO_TIMEOUT` | Client request timeout in seconds; unset means unlimited |
| `JEBALLTO_OUTPUT` | `table`, `json`, or `yaml` |
| `JEBALLTO_INSECURE` | Disable TLS certificate verification |

Global flags:

```text
--base-url, -u    Agent API base URL
--token, -t       Bearer token
--output, -o      table, json, or yaml
--timeout         Client request timeout in seconds
--insecure, -k    Disable TLS verification
--config, -c      Config file path
--version         Print version
```

Use `jeballto <command> --help` for complete Typer-generated help.

## Quick Start

```bash
# Check connectivity and authentication
jeballto health
jeballto auth verify

# Create a VM
jeballto vm create dev-vm --cpu 4 --memory 8GB --disk 64GB

# Install macOS from Apple's latest available IPSW
jeballto vm install start <vm-id> --wait

# Start the VM and open GUI
jeballto vm start <vm-id> --wait
jeballto vm gui open <vm-id>

# Run a command over SSH
jeballto vm execute <vm-id> "sw_vers"

# Stop and delete the VM
jeballto vm stop <vm-id> --wait
jeballto vm delete <vm-id> --yes
```

## Common Workflows

### Create From Image

```bash
jeballto image pull registry.example.com/macos:latest
jeballto vm create ci-vm --image registry.example.com/macos:latest --ephemeral
jeballto vm start <vm-id> --wait
```

When creating from an image, custom CPU, memory, or disk values are applied after create.

### Push VM Image

```bash
jeballto vm stop <vm-id> --wait
jeballto image push registry.example.com/macos:backup --vm <vm-id>
```

`image push` requires exactly one source:

- `--vm <vm-id>`
- `--image <image-id>`

### Long Image Operations

```bash
jeballto image pull registry.example.com/macos:latest --timeout 3600
jeballto image push registry.example.com/macos:backup --vm <vm-id> --timeout 7200
```

Without `--timeout`, image operations use no client-side timeout and the API operation timeout is omitted.

### Ephemeral VMs

```bash
jeballto vm create ci-vm --image registry.example.com/macos:latest --ephemeral
jeballto vm create short-lived --cpu 4 --memory 8GB --disk 64GB --ephemeral --lifetime 3600
```

Ephemeral VMs are intended for disposable workloads.

### Jeballtofile

Run inline steps:

```bash
jeballto jeballtofile run dev-vm \
  --steps '[{"type":"start"},{"type":"execute","command":"echo hello"}]' \
  --wait
```

Run from disk:

```bash
jeballto jeballtofile run --file ./Jeballtofile.yaml --wait
```

`--steps` and `--file` are mutually exclusive.

## Command Groups

| Group | Purpose |
|---|---|
| `health` | Check agent status |
| `auth` | Verify configured token |
| `vm` | VM create, update, lifecycle, SSH execution, GUI, VNC, events |
| `image` | OCI image list, pull, push, delete, wipe |
| `registry` | OCI registry login and logout |
| `config` | Read or update agent runtime config |
| `jeballtofile` | Run and inspect blueprint executions |
| `system` | Agent reset operations |

Common aliases:

- `vm ls`, `vm show`, `vm rm`, `vm exec`
- `image ls`, `image show`, `image rm`
- `jeballtofile ls`

## Output

```bash
jeballto vm list
jeballto --output json vm list
jeballto --output yaml vm list
```

`table` is default. Use `json` or `yaml` for scripts.

## Development

```bash
uv sync --dev
uv run jeballto --help
uv run ruff check .
uv run mypy
uv run pytest
```

## License

See [LICENSE](LICENSE).
