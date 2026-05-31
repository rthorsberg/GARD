"""NetBox REST integration (read-only in v1)."""

from gard.integrations.netbox.client import NetboxClient, NetboxDeviceRecord

__all__ = ["NetboxClient", "NetboxDeviceRecord"]
