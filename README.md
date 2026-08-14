# Network Automation Labs

Topology definitions and verification notes for the labs documented on my
[Lab Journal](https://anproit.com) — the "Network Automation with AI" series.

Each lab gets its own folder: a Netlab `topology.yml` to reproduce it, a
verification doc with the config and `show` output that proves it works,
and the full per-device running configs.

Note: `configs/` has the `username admin ... secret 9 ...` line stripped
from every device — everything else is the real running config.

## Labs

- [`vxlan_l2_l3_external/`](./vxlan_l2_l3_external) — Cisco IOS-XE VXLAN EVPN:
  L2VNI bridging, symmetric IRB L3VNI routing, VRF isolation, and eBGP-based
  external connectivity.
