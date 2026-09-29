# Sonos MCP Server

This project is a Sonos MCP (Model Context Protocol) server that allows you to control and interact with Sonos devices on your network. It provides various functionalities such as discovering devices, controlling playback, retrieving device states, and managing queues.

## Features

- Discover Sonos devices on the network
- Retrieve and control playback state for devices
- Manage playback queues
- Expose functionalities as MCP tools

## Requirements

- Python 3.12+
- `uv` for managing Python projects

## Installation

### From Git (Direct Install)
```bash
pip install git+https://github.com/WinstonFassett/sonos-mcp-server.git
```

### For Development

1. Clone the repository:
   ```bash
   git clone https://github.com/WinstonFassett/sonos-mcp-server.git
   cd sonos-mcp-server
   ```

2. Install the required dependencies using `uv`:
   ```bash
   uv sync
   ```

## Usage

### Running the Server

#### Stdio

Run the server using stdio:
```bash
uv run mcp run server.py
```

#### HTTP (streamable-http)

The server supports the MCP streamable-http transport natively (mcp SDK >= 1.12). No proxy needed:

```bash
SONOS_MCP_TRANSPORT=streamable-http \
SONOS_MCP_HOST=127.0.0.1 \
SONOS_MCP_PORT=8090 \
uv run sonos-mcp-server
```

Endpoint: `http://127.0.0.1:8090/mcp`

Environment variables:

| Var | Default | Notes |
|---|---|---|
| `SONOS_MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `SONOS_MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `SONOS_MCP_PORT` | `8000` | HTTP port (path is `/mcp`) |
| `SONOS_MCP_ALLOWED_HOSTS` | _(localhost only)_ | Extra Host headers to accept, comma-separated. Needed when serving behind a proxy with a different hostname (e.g. `mac-mini.tailc3138.ts.net:*`). |
| `SONOS_DEVICE_IPS` | _(SSDP discovery)_ | Comma-separated speaker IPs. Skips SSDP multicast and resolves names over unicast SOAP — required when the process can't multicast (e.g. launchd without Local Network permission). |

#### Legacy: SSE with supergateway

Older alternative (deprecated — prefer streamable-http above):

```bash
npx -y supergateway --port 8000 --stdio "uv run mcp run server.py"
```

### Development

To run the server in "development" mode with the MCP Inspector:

```bash
uv run mcp dev server.py
```

This command hosts an MCP Inspector for testing and debugging purposes.

To run the server with SSE in development mode, use the SSE command for supergateway, and in a second terminal window run:

```bash
npx @modelcontextprotocol/inspector
```

### Install in Claude Desktop

After publishing to git, users can install directly:

```bash
mcp install git+https://github.com/WinstonFassett/sonos-mcp-server.git
```

Or add to Claude Desktop config:
```json
{
  "mcpServers": {
    "sonos": {
      "command": "sonos-mcp-server"
    }
  }
}
```

### Available MCP Tools

Use the exposed MCP tools to interact with Sonos devices. The available tools include:

- `get_all_device_states`: Retrieve the state information for all discovered Sonos devices.
- `now_playing`: Retrieve information about currently playing tracks on all Sonos devices.
- `get_device_state`: Retrieve the state information for a specific Sonos device.
- `pause`, `stop`, `play`: Control playback on a Sonos device.
- `next`, `previous`: Skip tracks on a Sonos device.
- `get_queue`, `get_queue_length`: Manage the playback queue for a Sonos device.
- `mode`: Get or set the play mode of a Sonos device.
- `partymode`: Enable party mode on the current Sonos device.
- `speaker_info`: Retrieve speaker information for a Sonos device.
- `get_current_track_info`: Retrieve current track information for a Sonos device.
- `volume`: Get or set the volume of a Sonos device.
- `skip`, `play_index`, `remove_index_from_queue`: Manage tracks in the queue for a Sonos device.
- `add_service_tracks_to_queue`: Add tracks from music services like Spotify, Apple Music, Tidal, or Deezer to the Sonos queue.

## Publishing Updates

After making changes:

```bash
git add .
git commit -m "Description of changes"
git push
```

Users can update with:
```bash
pip install --upgrade git+https://github.com/WinstonFassett/sonos-mcp-server.git
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.