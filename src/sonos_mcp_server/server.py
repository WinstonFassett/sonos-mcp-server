"""Sonos MCP Server - Control Sonos speakers via Model Context Protocol."""

import base64
import os
import threading
import urllib.parse
from functools import lru_cache
from typing import Dict, List, Optional, Any, Literal, Union
import httpx
import soco
from soco.plugins.sharelink import ShareLinkPlugin
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import Response

# Extra Host-header names for HTTP transports (e.g. a Tailscale Serve
# hostname). The MCP SDK's DNS-rebinding protection rejects unknown hosts.
_extra_hosts = [
    h.strip()
    for h in os.environ.get("SONOS_MCP_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]

_transport_security = None
if _extra_hosts:
    _transport_security = TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"] + _extra_hosts,
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )

mcp = FastMCP(
    "Sonos",
    dependencies=["soco>=0.30.9"],
    host=os.environ.get("SONOS_MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("SONOS_MCP_PORT", "8000")),
    transport_security=_transport_security,
)
devices: Dict[str, soco.SoCo] = {}
device: Optional[soco.SoCo] = None

# soco's album_art URLs point at the speaker's own LAN IP (e.g.
# http://192.168.86.44:1400/getaa?...). Two separate problems follow:
#
# 1. That LAN IP is unreachable for anyone using an MCP client (e.g. an
#    Executor artifact) over Tailscale from off the home network -- Tailscale
#    isn't advertising a subnet route for the LAN.
# 2. Even once reachable, an Executor artifact's embedded view enforces an
#    `img-src data: blob:` CSP -- it refuses to load ANY remote image URL,
#    reachable or not. Only inline `data:`/`blob:` images render there (a
#    link opened in its own tab isn't under that CSP, which is why it "works
#    in a new tab" but not embedded).
#
# This server already runs on the LAN (it talks to the speakers directly)
# and is itself Tailscale-served, so it fetches the real image server-side
# and inlines it as a `data:` URI -- CSP-safe everywhere, and sidesteps the
# LAN-reachability problem too since the fetch happens here, not in the
# viewer's browser. `/album-art` is kept as a plain proxy route (reachable,
# but still subject to each viewer's own CSP) for anything that wants a
# plain URL instead, e.g. opening the image directly.
#
# SONOS_MCP_PUBLIC_URL overrides the derived base entirely. Otherwise it's
# derived from the first SONOS_MCP_ALLOWED_HOSTS entry (stripping a trailing
# ":*") plus SONOS_MCP_PORT. If neither is set, the /album-art fallback is
# skipped (data: URIs still work regardless, since they don't need a base URL).
def _public_base_url() -> str:
    override = os.environ.get("SONOS_MCP_PUBLIC_URL", "").strip()
    if override:
        return override.rstrip("/")
    if not _extra_hosts:
        return ""
    hostname = _extra_hosts[0].split(":")[0]
    port = os.environ.get("SONOS_MCP_PORT", "8000")
    return f"https://{hostname}:{port}"

_PUBLIC_BASE_URL = _public_base_url()

def _is_allowed_album_art_url(url: str) -> bool:
    """Restrict to the discovered devices' own IPs on port 1400 (the Sonos
    HTTP control port) -- both the data-URI fetch and the /album-art route
    are reachable over Tailscale, so neither may become an open proxy to
    arbitrary hosts."""
    parsed = urllib.parse.urlparse(url)
    allowed_ips = {d.ip_address for d in get_devices().values()}
    return parsed.scheme == "http" and parsed.hostname in allowed_ips and parsed.port == 1400

# Cached by URL: the same track's album art is polled repeatedly (every 2-15s)
# while it's playing, so this turns most polls into a dict lookup instead of
# a LAN round-trip. Bounded size evicts art for tracks no longer playing.
@lru_cache(maxsize=64)
def _fetch_album_art_data_uri(url: str) -> Optional[str]:
    if not _is_allowed_album_art_url(url):
        return None
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return None
    content_type = resp.headers.get("content-type", "image/jpeg")
    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:{content_type};base64,{b64}"

def _rewrite_album_art(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    if _PUBLIC_BASE_URL:
        return f"{_PUBLIC_BASE_URL}/album-art?u={urllib.parse.quote(url, safe='')}"
    return url

# Art never changes for a given track URL, and each speaker fetch takes ~1s, so keep
# recent images in memory. Oldest entries are dropped past _ART_CACHE_MAX.
_ART_CACHE: Dict[str, tuple] = {}
_ART_CACHE_MAX = 300

def _route_art_via_fast_speaker(url: str) -> str:
    """Fetch art from the speaker named by SONOS_MCP_ART_SPEAKER_IP, if set.

    Any speaker serves the same art for any track, and speakers differ a lot in
    speed (Patio ~3.5s vs ~1s for the others, same 179 KB image). The override
    must be one of the known speaker IPs; otherwise the URL is left unchanged.
    """
    ip = os.environ.get("SONOS_MCP_ART_SPEAKER_IP", "").strip()
    if not ip or ip not in {d.ip_address for d in get_devices().values()}:
        return url
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(netloc=f"{ip}:{parts.port or 1400}"))

@mcp.custom_route("/album-art", methods=["GET"])
async def album_art_proxy(request: Request) -> Response:
    """Fetch a speaker's album art server-side and stream it back as a plain
    URL (not inlined) -- for opening directly, outside an artifact's CSP."""
    target = request.query_params.get("u")
    if not target:
        return Response(status_code=400, content="missing u")
    if not _is_allowed_album_art_url(target):
        return Response(status_code=403, content="album art host not allowed")
    cache_key = target
    hit = _ART_CACHE.get(cache_key)
    if hit is not None:
        return Response(content=hit[0], media_type=hit[1],
                        headers={"Cache-Control": "public, max-age=86400", "X-Art-Cache": "hit"})
    target = _route_art_via_fast_speaker(target)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.get(target)
            upstream.raise_for_status()
    except Exception as e:
        return Response(status_code=502, content=f"upstream fetch failed: {e}")
    media_type = upstream.headers.get("content-type", "image/jpeg")
    _ART_CACHE[cache_key] = (upstream.content, media_type)
    while len(_ART_CACHE) > _ART_CACHE_MAX:
        _ART_CACHE.pop(next(iter(_ART_CACHE)))
    return Response(
        content=upstream.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400", "X-Art-Cache": "miss"},
    )

def discover_devices() -> Dict[str, soco.SoCo]:
    """Discover Sonos devices on the network and update the global devices dictionary.

    Discovery order:
    1. SONOS_DEVICE_IPS env var — comma-separated speaker IPs. Used when SSDP
       multicast is unavailable (e.g. launchd services without Local Network
       permission). Names are resolved over unicast SOAP, which always works.
    2. soco.discover() SSDP multicast. Returns None when multicast is blocked;
       that failure is tolerated and retried on the next call.

    Returns:
        Dict[str, soco.SoCo]: A dictionary mapping device names to their respective SoCo objects.
    """
    global devices
    ips = os.environ.get("SONOS_DEVICE_IPS", "").strip()
    if ips:
        found = []
        for ip in [ip.strip() for ip in ips.split(",") if ip.strip()]:
            try:
                found.append(soco.SoCo(ip))
            except Exception:
                continue
        devices = {d.player_name: d for d in found if d.player_name}
        return devices
    discovered = soco.discover()
    if discovered:
        devices = {d.player_name: d for d in discovered}
    return devices

def get_devices() -> Dict[str, soco.SoCo]:
    """Retrieve the dictionary of discovered Sonos devices.
    
    Returns:
        Dict[str, soco.SoCo]: A dictionary mapping device names to their respective SoCo objects.
    """
    global devices
    if not devices:
        discover_devices()
    return devices

def get_device(name: Optional[str] = None) -> soco.SoCo:
    """Retrieve a Sonos device by name or return the current device.
    
    Args:
        name: The name of the device to retrieve. If None, returns the current device.
        
    Returns:
        soco.SoCo: The Sonos device object.
        
    Raises:
        ValueError: If the specified device name is not found.
    """
    global device
    if not name and device:
        return device
    
    devices = get_devices()
    if not name:
        device = devices[list(devices.keys())[0]]
        return device
    
    if name in devices:
        device = devices[name]
        return device
    
    for key in devices:
        if key.lower() == name.lower():
            device = devices[key]
            return device
            
    raise ValueError(f"Device {name} not found")

def get_info_from(device: soco.SoCo) -> Dict[str, Any]:
    """Retrieve detailed information from a Sonos device.
    
    Args:
        device: The Sonos device to retrieve information from.
        
    Returns:
        Dict[str, Any]: A dictionary containing the device's name, volume, state, and current track information.
    """
    track_info = device.get_current_track_info()
    return {
        "name": device.player_name,
        "volume": device.volume,
        "state": device.get_current_transport_info()["current_transport_state"],
        "track": {
            "title": track_info.get("title"),
            "artist": track_info.get("artist"),
            "album": track_info.get("album"),
            "position": track_info.get("position"),
            "duration": track_info.get("duration"),
            "playlist_position": track_info.get("playlist_position"),
            "album_art": _rewrite_album_art(track_info.get("album_art"))
        }
    }

@mcp.tool()
def get_all_device_states() -> List[Dict[str, Any]]:
    """Retrieve the state information for all discovered Sonos devices.
    
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing state information for each device.
    """
    devices = get_devices()
    infos = []
    for device in devices.values():
        infos.append(get_info_from(device))
    return infos

@mcp.tool()
def now_playing() -> List[Dict[str, str]]:
    """Retrieve information about currently playing tracks on all Sonos devices.
    
    Returns:
        List[Dict[str, str]]: A list of dictionaries containing the name, title, artist, and album of currently playing tracks.
    """
    devices = get_devices()
    infos = []
    for device in devices.values():
        track = device.get_current_track_info()
        if not track:
            continue
        is_playing = device.get_current_transport_info()["current_transport_state"] == "PLAYING"
        if is_playing:
            infos.append({
                "name": device.player_name,
                "title": track["title"],
                "artist": track["artist"],
                "album": track["album"]
            })
    return infos

@mcp.tool()
def get_device_state(name: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve the state information for a specific Sonos device.
    
    Args:
        name: The name of the device to retrieve state information for. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: A dictionary containing the device's name, volume, state, and current track information.
    """
    device = get_device(name)
    return {
        "name": device.player_name,
        "volume": device.volume,
        "state": device.get_current_transport_info()["current_transport_state"],
        "track": device.get_current_track_info()
    }

@mcp.tool()
def pause(name: Optional[str] = None) -> Dict[str, Any]:
    """Pause playback on a Sonos device.
    
    Args:
        name: The name of the device to pause. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after pausing, including name, volume, state, and track info.
    """
    device = get_device(name).group.coordinator
    device.pause()
    return get_info_from(device)

@mcp.tool()
def stop(name: Optional[str] = None) -> Dict[str, Any]:
    """Stop playback on a Sonos device.
    
    Args:
        name: The name of the device to stop. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after stopping, including name, volume, state, and track info.
    """
    device = get_device(name).group.coordinator
    device.stop()
    return get_info_from(device)

@mcp.tool()
def play(name: Optional[str] = None) -> Dict[str, Any]:
    """Start playback on a Sonos device.
    
    Args:
        name: The name of the device to start playback on. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after starting playback, including name, volume, state, and track info.
    """
    device = get_device(name).group.coordinator
    device.play()
    return get_info_from(device)

@mcp.tool()
def next(name: Optional[str] = None) -> Dict[str, Any]:
    """Skip to the next track on a Sonos device.
    
    Args:
        name: The name of the device to skip the track on. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after skipping to the next track, including name, volume, state, and track info.
    """
    device = get_device(name).group.coordinator
    device.next()
    return get_info_from(device)

@mcp.tool()
def previous(name: Optional[str] = None) -> Dict[str, Any]:
    """Skip to the previous track on a Sonos device.
    
    Args:
        name: The name of the device to skip the track on. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after skipping to the previous track, including name, volume, state, and track info.
    """
    device = get_device(name).group.coordinator
    device.previous()
    return get_info_from(device)

def _queue_item_art_target(track: Any, speaker_ip: str) -> Optional[str]:
    """Return the speaker art URL for a queue item (absolute), or None.

    soco reports queue art as a relative path (/getaa?...); make it absolute on the speaker.
    """
    art = getattr(track, "album_art_uri", None)
    if not (isinstance(art, str) and art):
        return None
    if art.startswith("/"):
        art = f"http://{speaker_ip}:1400{art}"
    return art


def _queue_item_art_url(track: Any, speaker_ip: str) -> Optional[str]:
    """Return the queue item art as the same proxy URL track art uses, or None."""
    target = _queue_item_art_target(track, speaker_ip)
    return _rewrite_album_art(target) if target else None


_ART_WARM_LOCK = threading.Lock()


def _warm_art_cache(targets: List[str]) -> None:
    """Fetch these speaker art URLs one at a time into _ART_CACHE (best effort).

    A speaker serves one art request at a time, so fetching in the order the user
    will see them (current track first) beats letting a browser request all at once.
    Runs in a background thread; failures are skipped, the relay will retry on demand.
    """
    try:
        with httpx.Client(timeout=30) as client:
            for target in targets:
                if target in _ART_CACHE:
                    continue
                try:
                    upstream = client.get(_route_art_via_fast_speaker(target))
                    upstream.raise_for_status()
                except Exception:
                    continue
                _ART_CACHE[target] = (upstream.content, upstream.headers.get("content-type", "image/jpeg"))
                while len(_ART_CACHE) > _ART_CACHE_MAX:
                    _ART_CACHE.pop(next(iter(_ART_CACHE)))
    finally:
        _ART_WARM_LOCK.release()


def _start_art_warmup(targets: List[str]) -> None:
    """Start a background warm-up unless one is already running."""
    if not targets or not _ART_WARM_LOCK.acquire(blocking=False):
        return
    threading.Thread(target=_warm_art_cache, args=(targets,), daemon=True).start()


@mcp.tool()
def get_queue(
    name: Optional[str] = None,
    offset: Optional[Union[int, Literal["current"]]] = "current",
    limit: Optional[int] = 20,
    max_items: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Retrieve the queue of tracks for a Sonos device.
    
    Args:
        name: The name of the device to retrieve the queue from. If None, uses the current device.
        offset: The position to start retrieving tracks from:
               - If "current" (default): Start from the currently playing track
               - If 0: Start from the beginning of the queue
               - If positive integer: Start from that specific index
               - If negative integer: Start from that position from the end
        limit: Maximum number of items to return per request. Defaults to 20.
        max_items: Total maximum items to return. If None, returns all items within the limit.
                  Maximum allowed value is 500.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing track information in the queue.
    """
    sonos = get_device(name).group.coordinator
    current_position = int(sonos.get_current_track_info()['playlist_position'])
    queue_size = sonos.queue_size
    
    # Determine starting position
    start_position = 0
    if offset == "current":
        # Start from current track position
        start_position = max(0, current_position - 1)  # Convert to 0-based indexing
    elif isinstance(offset, int):
        if offset < 0:
            # Handle negative indexes (from the end)
            start_position = max(0, queue_size + offset)
        else:
            # Handle positive indexes
            start_position = offset
    
    # Calculate how many items to fetch
    items_to_fetch = limit
    if max_items is not None:
        # Cap max_items at 500
        max_items = min(500, max_items)
        items_to_fetch = min(limit, max_items)
    else:
        # If max_items not specified, still cap at 500
        items_to_fetch = min(limit, 500)
    
    # Ensure we don't go past the queue size
    end_position = min(start_position + items_to_fetch, queue_size)
    
    # Get the queue items
    tracks = sonos.get_queue(start=start_position, max_items=items_to_fetch)
    
    result = []
    art_targets = []
    for idx, track in enumerate(tracks):
        art_target = _queue_item_art_target(track, sonos.ip_address)
        if art_target:
            # current track first, then the rest in queue order
            if start_position + idx + 1 == current_position:
                art_targets.insert(0, art_target)
            else:
                art_targets.append(art_target)
        track_info = {
            "index": start_position + idx,  # Preserve actual queue index
            "title": track.title,
            "artist": track.creator,
            "album": track.album,
            "album_art": _rewrite_album_art(art_target) if art_target else None,
        }
        
        # Get duration safely, it might be in resources or as a direct attribute
        try:
            if hasattr(track, "duration"):
                track_info["duration"] = track.duration
            elif hasattr(track, "resources") and track.resources:
                for resource in track.resources:
                    if hasattr(resource, "duration") and resource.duration:
                        track_info["duration"] = resource.duration
                        break
        except:
            # If we can't get duration, just don't include it
            pass
            
        # Mark current track
        if start_position + idx + 1 == current_position:
            track_info["current"] = True
            
        result.append(track_info)

    _start_art_warmup(art_targets)
    return result

@mcp.tool()
def mode(
    mode: Optional[Literal["NORMAL", "SHUFFLE_NOREPEAT", "SHUFFLE", "REPEAT_ALL"]] = None, 
    name: Optional[str] = None
) -> str:
    """Get or set the play mode of a Sonos device.
    
    Args:
        mode: The play mode to set (e.g., "NORMAL", "SHUFFLE_NOREPEAT", "SHUFFLE", "REPEAT_ALL"). If None, returns the current mode.
        name: The name of the device to set the mode for. If None, uses the current device.
        
    Returns:
        str: The current play mode after the operation.
    """
    device = get_device(name).group.coordinator
    if mode:
        device.play_mode = mode
    return device.play_mode

@mcp.tool()
def partymode() -> Dict[str, Any]:
    """Enable party mode on the current Sonos device.
    
    Returns:
        Dict[str, Any]: The device's state after enabling party mode, including name, volume, state, and track info.
    """
    device = get_device()
    device.partymode()
    return get_info_from(device)

@mcp.tool()
def speaker_info(name: Optional[str] = None) -> Dict[str, str]:
    """Retrieve speaker information for a Sonos device.
    
    Args:
        name: The name of the device to retrieve speaker information from. If None, uses the current device.
        
    Returns:
        Dict[str, str]: A dictionary containing speaker information.
    """
    return get_device(name).get_speaker_info()

@mcp.tool()
def get_current_track_info(name: Optional[str] = None) -> Dict[str, str]:
    """Retrieve current track information for a Sonos device.
    
    Args:
        name: The name of the device to retrieve track information from. If None, uses the current device.
        
    Returns:
        Dict[str, str]: A dictionary containing the current track's artist, title, album, playlist position, and duration.
    """
    track = get_device(name).get_current_track_info()
    return {
        "artist": track['artist'],
        "title": track['title'],
        "album": track['album'],
        "playlist_position": track['playlist_position'],
        "duration": track['duration']
    }

@mcp.tool()
def volume(volume: Optional[int] = None, name: Optional[str] = None) -> int:
    """Get or set the volume of a Sonos device.
    
    Args:
        volume: The volume level to set (0-99). If None, returns current volume.
        name: The name of the device to control. If None, uses the current device.
        
    Returns:
        int: The current volume level after the operation.
        
    Raises:
        ValueError: If volume is not between 0 and 99.
        ValueError: If the specified device is not found.
    """
    device = get_device(name).group.coordinator
    if volume is not None:
        if not 0 <= volume <= 99:
            raise ValueError("Volume must be between 0 and 99")
        device.volume = volume
    return device.volume

@mcp.tool()
def skip(increment: int = 1, name: Optional[str] = None) -> Dict[str, Any]:
    """Skip tracks in the queue for a Sonos device.
    
    Args:
        increment: The number of tracks to skip forward. Defaults to 1.
        name: The name of the device to skip tracks on. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after skipping tracks, including name, volume, state, and track info.
        
    Raises:
        ValueError: If the new track position is out of the queue's range.
    """
    sonos = get_device(name).group.coordinator
    current = int(sonos.get_current_track_info()['playlist_position'])
    new_index = current + increment
    queue_length = sonos.queue_size
    
    if not 0 <= new_index < queue_length:
        raise ValueError(f"Cannot skip to position {new_index}")
    
    sonos.play_from_queue(new_index)
    return get_info_from(sonos)

@mcp.tool()
def play_index(index: int, name: Optional[str] = None) -> Dict[str, Any]:
    """Play a specific track from the queue on a Sonos device.
    
    Args:
        index: The index of the track to play.
        name: The name of the device to play the track on. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after playing the specified track, including name, volume, state, and track info.
        
    Raises:
        ValueError: If the index is out of the queue's range.
    """
    sonos = get_device(name).group.coordinator
    queue_length = sonos.queue_size
    
    if not 0 <= index <= queue_length:
        raise ValueError(f"Index {index} is not within range 1-{queue_length}")
    
    current = int(sonos.get_current_track_info()['playlist_position'])
    if index != current:
        sonos.play_from_queue(index)
    return get_info_from(sonos)

@mcp.tool()
def remove_index_from_queue(index: int, name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Remove a specific track from the queue on a Sonos device.
    
    Args:
        index: The index of the track to remove.
        name: The name of the device to remove the track from. If None, uses the current device.
        
    Returns:
        List[Dict[str, Any]]: The updated queue after removing the track.
        
    Raises:
        ValueError: If the index is out of the queue's range.
    """
    sonos = get_device(name).group.coordinator
    queue_length = sonos.queue_size
    
    if not 1 <= index <= queue_length:
        raise ValueError(f"Index {index} is not within range 1-{queue_length}")
    
    sonos.remove_from_queue(index)
    # Return the updated queue
    return get_queue(name)

def is_index_in_queue(index, queue_length):
    """Helper function to verify if an index exists within the queue length.
    
    Args:
        index: The index to check.
        queue_length: The total length of the queue.
        
    Returns:
        bool: True if the index is within the queue length, False otherwise.
    """
    if 0 <= index < queue_length:
        return True
    return False

def fetch_queue_length(sonos):
    """Return the queue length for a Sonos device.
    
    Args:
        sonos: The Sonos device to retrieve the queue length from.
        
    Returns:
        int: The length of the queue.
    """
    return sonos.queue_size

@mcp.tool()
def get_queue_length(name: Optional[str] = None) -> int:
    """Retrieve the queue length for a Sonos device.
    
    Args:
        name: The name of the device to retrieve the queue length from. If None, uses the current device.
        
    Returns:
        int: The length of the queue.
    """
    return fetch_queue_length(get_device(name))

@mcp.tool()
def add_service_tracks_to_queue(
    service: str,
    track_ids: str, 
    name: str,
    play_after_add: bool = False,
) -> Dict[str, Any]:
    """Add tracks from music services to the Sonos queue.
    
    Args:
        service: The music service name (e.g., 'spotify', 'apple', 'tidal', 'deezer', etc.)
        track_ids: A string of track IDs separated by newlines from the specified service.
                Example for Spotify: '6NmXV4o6bmp704aPGyTVVG\n2nGqLUUnLiTu93ltFV7BzC'
        play_after_add: Whether to start playing from the queue after adding the tracks. Defaults to False.
        name: The name of the device to add the tracks to. If None, uses the current device.
        
    Returns:
        Dict[str, Any]: The device's state after adding the tracks, including name, volume, state, and track info.
        
    Raises:
        ValueError: If the device is not found or the track IDs are invalid.
    """
    import logging
    logger = logging.getLogger(__name__)
    device = get_device(name).group.coordinator
    sharelink = ShareLinkPlugin(device)
    
    # Split track IDs by newlines
    track_ids_list = track_ids.strip().split("\n")
    
    # Format service track links
    service = service.lower()
    links = [f"{service}:track:{track_id.strip()}" for track_id in track_ids_list if track_id.strip()]
    
    # Add each link to the queue
    queue_positions = []
    for link in links:
        try:
            position = sharelink.add_share_link_to_queue(link)
            queue_positions.append(position)
        except Exception as e:
            raise ValueError(f"Failed to add track {link}: {str(e)}")
    
    # Play the first added track if requested
    if play_after_add and queue_positions:
        device.play_from_queue(queue_positions[0] - 1)  # Adjust for 0-based indexing
    
    return get_info_from(device)

def main():
    """Main entry point for the server.

    Transport is selected via SONOS_MCP_TRANSPORT (stdio | sse |
    streamable-http). HTTP bind address comes from SONOS_MCP_HOST and
    SONOS_MCP_PORT (defaults 127.0.0.1:8000, path /mcp).
    """
    try:
        discover_devices()
        device = get_device()
    except Exception as e:
        # Discovery can fail at startup (e.g. SSDP blocked under launchd).
        # Devices are discovered lazily on each tool call via get_devices().
        print(f"Startup discovery failed, will retry lazily: {e}")
    transport = os.environ.get("SONOS_MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)  # type: ignore[arg-type]

if __name__ == "__main__":
    main()