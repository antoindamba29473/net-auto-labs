import os
import pynetbox
import requests

from dotenv import load_dotenv
from netmiko import ConnectHandler
from pprint import pprint
from fastmcp import FastMCP


load_dotenv()


# =============================================================================
# Configuration
# =============================================================================

NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

NETBOX_GRAPHQL_URL = f"{NETBOX_URL.rstrip('/')}/graphql/"

mcp = FastMCP("network-agent-tools")

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

devices = {}


# =============================================================================
# NetBox GraphQL
# =============================================================================

def query_netbox_graphql(query: str, variables: dict | None = None):
    """
    Execute a read-only GraphQL query against NetBox.
    """

    headers = {
        "Authorization": f"Token {NETBOX_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "variables": variables or {},
    }

    try:
        response = requests.post(
            NETBOX_GRAPHQL_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

    except requests.RequestException as e:
        raise RuntimeError(f"NetBox GraphQL request failed: {e}")

    result = response.json()

    if "errors" in result:
        raise RuntimeError(
            f"NetBox GraphQL error: {result['errors']}"
        )

    return result.get("data", {})


# =============================================================================
# Get devices from NetBox
# =============================================================================

def query_netbox_devices():
    """
    Query the NetBox device inventory using pynetbox.
    """

    devices.clear()

    for device in nb.dcim.devices.all():

        primary_ip = (
            str(device.primary_ip.address) if device.primary_ip else None
        )

        # Only include devices in the 172.20.20.0/24 network
        if primary_ip and primary_ip.startswith("172.20.20."):

            devices[device.name.upper()] = {
                "role": device.role.name if device.role else None,
                "device_type": device.platform.slug if device.platform else None,
                "primary_ip": primary_ip,
                "username": os.getenv("USERNAME"),
                "password": os.getenv("PASSWORD"),
            }

    # print("\nDevices found in NetBox:")
    # pprint(devices)

    return devices


# =============================================================================
# Get device configuration detail from NetBox (VLANs, VRFs, IPs)
# =============================================================================

def query_netbox_device_config(device_name: str):
    """
    Query NetBox via GraphQL for one device's interfaces, including
    VLAN mode, tagged/untagged VLANs, VRF, and IP addresses.
    """

    query = """
    query ($name: String!) {
        device_list(filters: {name: {exact: $name}}) {
            name
            interfaces {
                name
                description
                enabled
                mode
                untagged_vlan { vid name }
                tagged_vlans { vid name }
                vrf { name rd }
                ip_addresses { address }
            }
        }
    }
    """

    data = query_netbox_graphql(query, {"name": device_name})

    results = data.get("device_list", [])

    if not results:
        return {
            "error": f"Device '{device_name}' not found in NetBox.",
        }

    return results[0]


# =============================================================================
# Safety helpers
# =============================================================================

BLOCKED_COMMAND_WORDS = [
    "configure",
    "conf t",
    "copy",
    "delete",
    "erase",
    "format",
    "reload",
    "reboot",
    "write",
    "wr mem",
    "commit",
    "replace",
    "install",
    "bash",
    "sudo",
    "python",
    "tclsh",
    "guestshell",
]


# Commands that can reveal secrets or generate very large output.
BLOCKED_SHOW_PATTERNS = [
    "show running-config",
    "show startup-config",
    "show tech",
    "show tech-support",
]


def normalize_command(command: str) -> str:
    """Normalize whitespace for safer command validation."""

    return " ".join(command.strip().split())


def is_safe_show_command(command: str) -> bool:
    """
    Allow only read-only show commands and block risky variants.
    """

    normalized = normalize_command(command).lower()

    # Must start with "show "
    if not normalized.startswith("show "):
        return False

    # Block dangerous keywords
    for blocked in BLOCKED_COMMAND_WORDS:
        if blocked in normalized:
            return False

    # Block sensitive show commands
    for blocked in BLOCKED_SHOW_PATTERNS:

        # Catches abbreviations such as:
        # show run
        # show running-config

        if (
            normalized.startswith(blocked)
            or blocked.startswith(normalized)
        ):
            return False

    # Avoid command chaining or shell-like behavior
    if any(
        token in normalized
        for token in [";", "&&", "||", "`", "$("]
    ):
        return False

    return True


# =============================================================================
# Network device connection
# =============================================================================

def connect_and_run(device_name, command):

    device_name = device_name.strip().upper()

    # Refresh NetBox inventory if necessary
    if not devices:
        query_netbox_devices()

    # -------------------------------------------------------------------------
    # Select devices
    # -------------------------------------------------------------------------

    if device_name == "ALL":

        selected_devices = devices

    elif device_name in devices:

        selected_devices = {
            device_name: devices[device_name]
        }

    else:

        return {
            "error": f"Device '{device_name}' not found.",
            "available_devices": list(devices.keys()),
        }

    # -------------------------------------------------------------------------
    # Connect to selected devices
    # -------------------------------------------------------------------------

    results = {}

    for name, device in selected_devices.items():

        print(
            f"\nConnecting to {name} "
            f"({device['primary_ip']})..."
        )

        connection_data = {
            "device_type": device["device_type"],

            "host": device["primary_ip"].split("/")[0],

            "username": device["username"],

            "password": device["password"],
        }

        try:

            connection = ConnectHandler(**connection_data)

            print(f"Connected to {name}")

            output = connection.send_command(command)

            connection.disconnect()

            print(f"\n--- {command} ---")
            print(output)

            results[name] = output

        except Exception as e:

            print(
                f"Error connecting to {name}: {e}"
            )

            results[name] = {
                "error": str(e)
            }

    return results


# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool()
def get_netbox_devices():
    """
    Return the NetBox device inventory.

    Returns device name, role, platform/device type,
    and primary IP address.
    """

    query_netbox_devices()

    return {
        name: {
            key: value
            for key, value in device.items()
            if key not in ("username", "password")
        }
        for name, device in devices.items()
    }


@mcp.tool()
def get_netbox_device_information(device_name: str):
    """
    Return one device's configuration information from NetBox:
    interfaces, VLAN mode, tagged/untagged VLANs, VRF, and IP addresses.

    Pass the device name directly - no need to call get_netbox_devices()
    first to verify it exists; an unknown device name returns a clear
    "not found" error instead of failing silently.
    """

    return query_netbox_device_config(device_name.strip().upper())


@mcp.tool()
def execute_command(device_name: str, command: str):
    """
    Run a read-only 'show' command on a network device.

    Configuration and write commands are rejected.
    """

    command = normalize_command(command)

    if not is_safe_show_command(command):

        return {
            "error": (
                f"Command rejected: "
                f"'{command}' is not an allowed "
                f"read-only show command."
            )
        }

    return connect_and_run(
        device_name,
        command
    )


# =============================================================================
# Start MCP server
# =============================================================================

if __name__ == "__main__":
    mcp.run()