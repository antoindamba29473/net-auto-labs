import os
import pynetbox
from dotenv import load_dotenv
from netmiko import ConnectHandler
from pprint import pprint
from fastmcp import FastMCP

load_dotenv()

# Configuration
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

mcp = FastMCP("network-agent-tools")

nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)

devices = {}

# -----------------------------------------------------------------------------
# Safety helpers
# -----------------------------------------------------------------------------

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
    """Allow only read-only show commands and block risky variants."""
    normalized = normalize_command(command).lower()

    if not normalized.startswith("show "):
        return False

    for blocked in BLOCKED_COMMAND_WORDS:
        if blocked in normalized:
            return False

    for blocked in BLOCKED_SHOW_PATTERNS:
        # Catches IOS command abbreviations (e.g. "show run" for
        # "show running-config") by checking the prefix relationship
        # in both directions, not just the typed text being the longer one.
        if normalized.startswith(blocked) or blocked.startswith(normalized):
            return False

    # Avoid command chaining or unexpected shell-like behavior.
    if any(token in normalized for token in [";", "&&", "||", "`", "$("]):
        return False

    return True

# Get devices from NetBox
def get_netbox_device():
    for device in nb.dcim.devices.all():

        primary_ip = str(device.primary_ip.address) if device.primary_ip else None

        if primary_ip and primary_ip.startswith("172.20.20."):

            devices[device.name] = {
                "role": device.role.name if device.role else None,
                "device_type": device.platform.slug if device.platform else None,
                "primary_ip": primary_ip,
                "username": os.getenv("USERNAME"),
                "password": os.getenv("PASSWORD")
            }

    # Display devices found in NetBox
    print("\nDevices found in NetBox:")
    pprint(devices)
    return devices


def connect_and_run(device_name, command):
    device_name = device_name.strip().upper()

    if not devices:
        get_netbox_device()

    # Select devices
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

    # Connect to selected device(s)
    results = {}

    for name, device in selected_devices.items():

        print(f"\nConnecting to {name} ({device['primary_ip']})...")

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

            print(f"Error connecting to {name}: {e}")
            results[name] = {"error": str(e)}

    return results

@mcp.tool()
def get_netbox_devices():
    """Return the NetBox device inventory (name, role, device_type, primary_ip) used for connecting to devices"""
    get_netbox_device()
    return {
        name: {k: v for k, v in device.items() if k not in ("username", "password")}
        for name, device in devices.items()
    }

@mcp.tool()
def execute_command(device_name: str, command: str):
    """Run a read-only 'show' command on a device and return its raw output. Config/write commands are rejected."""
    command = normalize_command(command)

    if not is_safe_show_command(command):
        return {
            "error": f"Command rejected: '{command}' is not an allowed read-only show command."
        }

    return connect_and_run(device_name, command)


if __name__ == "__main__":
        mcp.run()