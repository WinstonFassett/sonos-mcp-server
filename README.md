# Sonos MCP Server

This project is a Sonos MCP (Model Context Protocol) server that allows you to control and interact with Sonos devices on your network. It provides various functionalities such as discovering devices, controlling playback, retrieving device states, and managing queues.

## Features

- Discover Sonos devices on the network
- Retrieve and control playback state for devices
- Manage playback queues
- Expose functionalities as MCP tools

## Requirements

- Python 3.7+
- `uv` for managing Python projects

## Installation

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

#### SSE with Supergateway

Run the server with SSE using the `supergateway` tool:

```bash
npx -y supergateway --port 8000 --stdio "uv run mcp run server.py"
```

Alternatively, you can use the convenience script provided in the repository:

```bash
./npx-serve-sse-8000.sh
```

### Development

To run the server in "development" mode with the MCP Inspector:

```bash
uv run mcp dev server.py
```

This command hosts an MCP Inspector for testing and debugging purposes.

To run the server with SSE in development mode, use the SSE command for supergateway, and in a second terminal windor run:

```bash
npx @modelcontextprotocol/inspector
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

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
