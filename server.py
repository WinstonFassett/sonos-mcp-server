from typing import Dict, List, Optional, Any, Literal
from mcp.server.fastmcp import FastMCP
import soco

mcp = FastMCP("Sonos", dependencies=["soco"])
devices: Dict[str, soco.SoCo] = {}
device: Optional[soco.SoCo] = None

def discover_devices() -> Dict[str, soco.SoCo]:
    """Discover Sonos devices on the network and update the global devices dictionary.
    
    Returns:
        Dict[str, soco.SoCo]: A dictionary mapping device names to their respective SoCo objects.
    """
    global devices
    devices = {device.player_name: device for device in soco.discover()}
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
            "album_art": track_info.get("album_art")
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
    device = get_device(name)
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
    device = get_device(name)
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
    device = get_device(name)
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
    device = get_device(name)
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
    device = get_device(name)
    device.previous()
    return get_info_from(device)

@mcp.tool()
def get_queue(name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve the queue of tracks for a Sonos device.
    
    Args:
        name: The name of the device to retrieve the queue from. If None, uses the current device.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing track information in the queue.
    """
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
    """Get or set the play mode of a Sonos device.
    
    Args:
        mode: The play mode to set (e.g., "NORMAL", "SHUFFLE_NOREPEAT", "SHUFFLE", "REPEAT_ALL"). If None, returns the current mode.
        name: The name of the device to set the mode for. If None, uses the current device.
        
    Returns:
        str: The current play mode after the operation.
    """
    device = get_device(name)
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
    device = get_device(name)
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
    sonos = get_device(name)
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

def main():
    discover_devices()
    device = get_device()


if __name__ == "__main__":
    main()
