"""NetBox plugin configuration for GARD platform lab (F13).

Mounted into the NetBox container at /etc/netbox/config/plugins.py when
GARD_NETBOX_PLATFORM=1 (see docker-compose.platform.yml).
"""

from __future__ import annotations

import os

_branching = os.environ.get("GARD_NETBOX_BRANCHING_ENABLED", "0") == "1"

PLUGINS: list[str] = ["netbox_diode_plugin"]
if _branching:
    PLUGINS.append("netbox_branching")

PLUGINS_CONFIG = {
    "netbox_diode_plugin": {
        "diode_target_override": os.environ.get(
            "DIODE_GRPC_TARGET",
            "grpc://diode-nginx:80/diode",
        ),
        "diode_username": os.environ.get("DIODE_NETBOX_USERNAME", "diode"),
        "netbox_to_diode_client_secret": os.environ.get("NETBOX_TO_DIODE_CLIENT_SECRET", ""),
    },
}

if _branching:
    DATABASE_ROUTERS = [
        "netbox_branching.database.BranchAwareRouter",
    ]
