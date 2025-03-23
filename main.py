from typing import Dict, List, Optional, Any, Literal
from mcp.server.fastmcp import FastMCP
import soco

mcp = FastMCP("Sonos", dependencies=["soco"])
devices: Dict[str, soco.SoCo] = {}
device: Optional[soco.SoCo] = None

def discover_devices() -> Dict[str, soco.SoCo]:
    global devices
    devices = {device.player_name: device for device in soco.discover()}
    return devices

def get_devices() -> Dict[str, soco.SoCo]:
    global devices
    if not devices:
        discover_devices()
    return devices


def get_device(name: Optional[str] = None) -> soco.SoCo:
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

@mcp.tool()
def get_device_names() -> List[str]:
    return list(get_devices().keys())


def get_info_from(device: soco.SoCo) -> Dict[str, Any]:
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
            "album_art": track_info.get("album_art")
        }
    }

@mcp.tool()
def get_all_device_states() -> List[Dict[str, Any]]:
    devices = get_devices()
    infos = []
    for device in devices.values():
        infos.append(get_info_from(device))
    return infos

@mcp.tool()
def now_playing() -> List[Dict[str, str]]:
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
    device = get_device(name)
    return {
        "name": device.player_name,
        "volume": device.volume,
        "state": device.get_current_transport_info()["current_transport_state"],
        "track": device.get_current_track_info()
    }

@mcp.tool()
def pause(name: Optional[str] = None) -> None:
    get_device(name).pause()

@mcp.tool()
def stop(name: Optional[str] = None) -> None:
    get_device(name).stop()

@mcp.tool()
def play(name: Optional[str] = None) -> None:
    get_device(name).play()

@mcp.tool()
def next(name: Optional[str] = None) -> None:
    get_device(name).next()

@mcp.tool()
def previous(name: Optional[str] = None) -> None:
    get_device(name).previous()

@mcp.tool()
def get_queue(name: Optional[str] = None) -> List[Dict[str, Any]]:
    sonos = get_device(name)
    tracks = sonos.get_queue()
    current = int(sonos.get_current_track_info()['playlist_position'])
    return [{
        "index": idx-1,
        "title": track.title,
        "artist": track.creator,
        "album": track.album,
        **({"current": True} if idx == current else {})
    } for idx, track in enumerate(tracks, 1)]

@mcp.tool()
def mode(
    mode: Optional[Literal["NORMAL", "SHUFFLE_NOREPEAT", "SHUFFLE", "REPEAT_ALL"]] = None, 
    name: Optional[str] = None
) -> str:
    device = get_device(name)
    if mode:
        device.play_mode = mode
    return device.play_mode

@mcp.tool()
def partymode() -> None:
    get_device().partymode()

@mcp.tool()
def speaker_info(name: Optional[str] = None) -> Dict[str, str]:
    return get_device(name).get_speaker_info()

@mcp.tool()
def get_current_track_info(name: Optional[str] = None) -> Dict[str, str]:
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
    device = get_device(name)
    if volume is not None:
        if not 0 <= volume <= 99:
            raise ValueError("Volume must be between 0 and 99")
        device.volume = volume
    return device.volume

@mcp.tool()
def skip(increment: int = 1, name: Optional[str] = None) -> None:
    sonos = get_device(name)
    current = int(sonos.get_current_track_info()['playlist_position'])
    new_index = current + increment
    queue_length = sonos.queue_size
    
    if not 0 <= new_index < queue_length:
        raise ValueError(f"Cannot skip to position {new_index}")
    
    sonos.play_from_queue(new_index)

@mcp.tool()
def play_index(index: int, name: Optional[str] = None) -> None:
    sonos = get_device(name).group.coordinator
    queue_length = sonos.queue_size
    
    if not 0 <= index <= queue_length:
        raise ValueError(f"Index {index} is not within range 1-{queue_length}")
    
    current = int(sonos.get_current_track_info()['playlist_position'])
    if index != current:
        sonos.play_from_queue(index)

@mcp.tool()
def remove_index_from_queue(index: int, name: Optional[str] = None) -> None:
    sonos = get_device(name).group.coordinator
    queue_length = sonos.queue_size
    
    if not 1 <= index <= queue_length:
        raise ValueError(f"Index {index} is not within range 1-{queue_length}")
    
    sonos.remove_from_queue(index)

def is_index_in_queue(index, queue_length):
    """Helper function to verify if index exists"""
    if 0 <= index <  queue_length:
        return True
    return False

def fetch_queue_length(sonos):
    """Return the queue length"""
    return sonos.queue_size

@mcp.tool()
def get_queue_length(name: Optional[str] = None) -> int:
    return fetch_queue_length(get_device(name))

def main():
    discover_devices()
    device = get_device()


if __name__ == "__main__":
    main()
