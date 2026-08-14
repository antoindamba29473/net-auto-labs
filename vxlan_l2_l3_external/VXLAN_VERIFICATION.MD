# VXLAN EVPN — L2VNI / L3VNI configuration and verification

Cisco IOS-XE (IOL), EVPN-VXLAN with static BUM replication, 2 spines / 4 leafs, two tenant VRFs (`customer-a`, `customer-b`).

## Topology

| Host | VRF | VLAN | Subnet | Leaf |
|---|---|---|---|---|
| H-100-10-7-L1 | customer-a | 100 | 172.16.10.0/24 | L1 |
| H-100-10-8-L2 | customer-a | 100 | 172.16.10.0/24 | L2 |
| H-101-11-7-L1 | customer-a | 101 | 172.16.11.0/24 | L1 |
| H-102-12-7-L3 | customer-a | 102 | 172.16.12.0/24 | L3 |
| H-200-20-7-L3 | customer-b | 200 | 172.16.20.0/24 | L3 |
| H-200-20-8-L4 | customer-b | 200 | 172.16.20.0/24 | L4 |
| H-201-21-7-L3 | customer-b | 201 | 172.16.21.0/24 | L3 |
| H-202-22-7-L1 | customer-b | 202 | 172.16.22.0/24 | L1 |
| EXT / HE | — | external | behind EXT router | — |

`customer-a` L3VNI: 50001. `customer-b` L3VNI: 60001.

## Reachability matrix

| Source | Destination | Mechanism | Why | Result |
|---|---|---|---|---|
| H-100-10-7-L1 | H-100-10-8-L2 | L2VNI | same VLAN 100, different leaf (L1/L2) | ✅ 0% loss |
| H-100-10-7-L1 | H-101-11-7-L1 | Local IRB (no VXLAN) | different VLAN, same leaf (L1 has both locally) | ✅ 0% loss |
| H-100-10-7-L1 | H-102-12-7-L3 | L3VNI (symmetric IRB) | different VLAN + different leaf; L1 has no VLAN102 locally | ✅ 0% loss |
| H-100-10-8-L2 | H-101-11-7-L1 | L3VNI (symmetric IRB) | L2 has no VLAN101 locally | not yet tested |
| H-100-10-8-L2 | H-102-12-7-L3 | L3VNI (symmetric IRB) | L2 has no VLAN102 locally | not yet tested |
| H-101-11-7-L1 | H-102-12-7-L3 | L3VNI (symmetric IRB) | neither leaf has the other's VLAN locally | not yet tested |
| H-200-20-7-L3 | H-200-20-8-L4 | L2VNI | same VLAN 200, different leaf (L3/L4) | ✅ 0% loss |
| H-200-20-7-L3 | H-201-21-7-L3 | Local IRB (no VXLAN) | different VLAN, same leaf (L3 has both locally) | ✅ 0% loss |
| H-200-20-7-L3 | H-202-22-7-L1 | L3VNI (symmetric IRB) | different VLAN + different leaf; L3 has no VLAN202 locally | ✅ 0% loss |
| H-200-20-8-L4 | H-201-21-7-L3 | L3VNI (symmetric IRB) | L4 has no VLAN201 locally | not yet tested |
| H-200-20-8-L4 | H-202-22-7-L1 | L3VNI (symmetric IRB) | L4 has no VLAN202 locally | not yet tested |
| H-201-21-7-L3 | H-202-22-7-L1 | L3VNI (symmetric IRB) | neither leaf has the other's VLAN locally | not yet tested |
| any customer-a host | any customer-b host | VRF isolation | no route leaking configured between VRFs | ❌ 100% loss (expected) |
| HE | customer-b hosts | eBGP, vrf customer-b | built for customer-b; customer-a not yet | ✅ 0% loss (both directions) |

Rows marked "not yet tested" follow the same mechanism as an already-confirmed row in the same VRF and are expected to behave identically.

## L2VNI

Config (per leaf, per VLAN):
```
l2vpn evpn instance 100 vlan-based
 encapsulation vxlan
 route-target export 100:10100
 route-target import 100:10100
 no auto-route-target
vlan configuration 100
 member evpn-instance 100 vni 10100
```
`interface nve1` then maps the VNI to a multicast group for BUM traffic:
```
interface nve1
 member vni 10100 mcast-group 239.0.0.100
```

**Verification — ping (H-100-10-7-L1 → H-100-10-8-L2, 172.16.10.8):**
```
PING 172.16.10.8 (172.16.10.8): 56 data bytes
64 bytes from 172.16.10.8: seq=0 ttl=64 time=1.778 ms
64 bytes from 172.16.10.8: seq=1 ttl=64 time=1.725 ms
64 bytes from 172.16.10.8: seq=2 ttl=64 time=1.981 ms
64 bytes from 172.16.10.8: seq=3 ttl=64 time=1.630 ms

--- 172.16.10.8 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
```
TTL stayed at 64 — confirms the packet was bridged, not routed.

**Verification — BGP EVPN Type-2 route for the remote host, on L1:**
```
show bgp l2vpn evpn
Route Distinguisher: 10.0.0.2:100
 *>i  [2][10.0.0.2:100][0][48][AAC1ABCF3C43][0][*]/20
                      10.0.0.2                 0    100      0 ?
```
`10.0.0.2` is `L2`'s loopback/VTEP — confirms the MAC was learned via EVPN from the remote leaf, not a local port.

**Verification — MAC address table on L1:**
```
show mac address-table vlan 100
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
 100    aac1.ab15.c28d    DYNAMIC     Et0/3
 100    aac1.abff.44c6    DYNAMIC     Et0/3
```

## L3VNI

Requires, per leaf, per VRF: a VRF definition with matching RD/route-target ("stitching") on every leaf that shares the VRF, an L3VNI-anchor SVI, and an `nve1` binding of the L3VNI to the VRF.

```
vrf definition customer-a
 rd 65000:1
 route-target export 65000:1
 route-target import 65000:1
 address-family ipv4
  route-target export 65000:1 stitching
  route-target import 65000:1 stitching
 exit-address-family

interface Vlan501
 description cust-a svi for l3vni
 vrf forwarding customer-a
 ip address 99.99.1.1 255.255.255.0
 no autostate

interface nve1
 member vni 50001 vrf customer-a

router bgp 65000
 address-family ipv4 vrf customer-a
  advertise l2vpn evpn
  redistribute connected
 exit-address-family
```

Two notes worth keeping in the writeup, since they're the actual failure points:

1. **`advertise l2vpn evpn` is not implied by anything else.** Without it under `address-family ipv4 vrf customer-a`, the VRF's IPv4 routes stay local — they never get redistributed into BGP L2VPN EVPN as Type-5 routes, so remote leafs never learn them at all, no matter how correct the RD/route-target/VNI config is.
2. **The L3VNI-anchor SVI (`interface Vlan501`) needs `no autostate`.** This SVI has no physical ports (it only exists to anchor the L3VNI to the VRF), so IOS-XE's default autostate behavior keeps it administratively/line-protocol down, which breaks the L3VNI path even with correct BGP config.

**Verification — ping (H-100-10-7-L1 → H-102-12-7-L3, 172.16.12.7):**
```
PING 172.16.12.7 (172.16.12.7): 56 data bytes
64 bytes from 172.16.12.7: seq=0 ttl=63 time=1.833 ms
64 bytes from 172.16.12.7: seq=1 ttl=63 time=2.071 ms
64 bytes from 172.16.12.7: seq=2 ttl=63 time=1.965 ms
64 bytes from 172.16.12.7: seq=3 ttl=63 time=1.985 ms

--- 172.16.12.7 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
```
TTL dropped to 63 — confirms the packet was actually routed (one hop), unlike the L2VNI case above.

**Verification — ping (H-200-20-7-L3 → H-202-22-7-L1, 172.16.22.7):**
```
PING 172.16.22.7 (172.16.22.7): 56 data bytes
64 bytes from 172.16.22.7: seq=0 ttl=63 time=1.947 ms
64 bytes from 172.16.22.7: seq=1 ttl=63 time=2.069 ms
64 bytes from 172.16.22.7: seq=2 ttl=63 time=1.996 ms
64 bytes from 172.16.22.7: seq=3 ttl=63 time=2.139 ms
64 bytes from 172.16.22.7: seq=4 ttl=63 time=2.082 ms

--- 172.16.22.7 ping statistics ---
5 packets transmitted, 5 packets received, 0% packet loss
```

**Verification — BGP EVPN Type-5 route on L1 (learned from L3):**
```
show bgp l2vpn evpn route-type 5
Route Distinguisher: 65000:1 (default for vrf customer-a)
 *>i  [5][65000:1][0][24][172.16.12.0]/17
                      10.0.0.3 ...
```

**Verification — RIB entry on L1:**
```
show ip route vrf customer-a 172.16.12.0
Routing entry for 172.16.12.0/24
  Known via "bgp 65000", distance 200, metric 0, type internal
  Last update from 10.0.0.3 on Vlan501, ... ago
  * 10.0.0.3 (default), from 10.0.0.5, ... via Vlan501
```

## VRF isolation

customer-a and customer-b are not leaked into each other — confirmed with H-100-10-7-L1 → H-200-20-7-L3 (172.16.20.7):
```
PING 172.16.20.7 (172.16.20.7): 56 data bytes

--- 172.16.20.7 ping statistics ---
3 packets transmitted, 0 packets received, 100% packet loss
```

## External connectivity

Built and working for `customer-b`. `customer-a` is not configured yet, but the same recipe applies — see the note at the end.

**Design**

The `L4`↔`EXT` link is a member interface of `customer-b`'s VRF on both ends. `L4` has it in `customer-b` like any other VRF interface. `EXT` — normally just a plain external router — got a matching local `vrf definition customer-b` too, with both its interfaces (`L4`-facing and `HE`-facing) inside it. `L4` and `EXT` then peer over genuine eBGP (`L4` in AS 65000, `EXT` in AS 65500) inside that VRF, so routes flow dynamically in both directions instead of via static leaking.

```
customer-b (L3VNI 60001)
      |
     L4  ---- eBGP (AS 65000 <-> AS 65500), vrf customer-b ----  EXT  ----  HE
```

**Config — L4:**
```
interface Ethernet0/3
 description L4 -> EXT
 vrf forwarding customer-b
 ip address 10.255.0.1 255.255.255.252

ip route vrf customer-b 0.0.0.0 0.0.0.0 10.255.0.2 name Route-2-External

router bgp 65000
 address-family ipv4 vrf customer-b
  advertise l2vpn evpn
  redistribute connected
  neighbor EXTERNAL peer-group
  neighbor EXTERNAL remote-as 65500
  neighbor EXTERNAL send-community both
  neighbor 10.255.0.2 peer-group EXTERNAL
  neighbor 10.255.0.2 activate
 exit-address-family
```

**Config — EXT:**
```
vrf definition customer-b
 rd 65000:2
 address-family ipv4
 exit-address-family

interface Ethernet0/1
 description EXT -> L4
 vrf forwarding customer-b
 ip address 10.255.0.2 255.255.255.252

interface Ethernet0/2
 description EXT -> HE
 vrf forwarding customer-b
 ip address 172.16.0.16 255.255.255.0

router bgp 65500
 address-family ipv4 vrf customer-b
  network 172.16.0.0 mask 255.255.255.0
  neighbor EXTERNAL peer-group
  neighbor EXTERNAL remote-as 65000
  neighbor EXTERNAL send-community both
  neighbor 10.255.0.1 peer-group EXTERNAL
  neighbor 10.255.0.1 activate
 exit-address-family
```

**Verification — HE → customer-b host directly on L4 (172.16.20.8):**
```
PING 172.16.20.8 (172.16.20.8): 56 data bytes
64 bytes from 172.16.20.8: seq=0 ttl=63 time=2.132 ms
64 bytes from 172.16.20.8: seq=1 ttl=63 time=2.053 ms
64 bytes from 172.16.20.8: seq=2 ttl=63 time=2.131 ms
64 bytes from 172.16.20.8: seq=3 ttl=63 time=8.187 ms

--- 172.16.20.8 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
```

**Verification — HE → customer-b host across the fabric, via true L3VNI to L1 (172.16.22.7):**
```
PING 172.16.22.7 (172.16.22.7): 56 data bytes
64 bytes from 172.16.22.7: seq=0 ttl=62 time=1.927 ms
64 bytes from 172.16.22.7: seq=1 ttl=62 time=1.741 ms
64 bytes from 172.16.22.7: seq=2 ttl=62 time=1.873 ms
64 bytes from 172.16.22.7: seq=3 ttl=62 time=1.879 ms

--- 172.16.22.7 ping statistics ---
4 packets transmitted, 4 packets received, 0% packet loss
```
Note the TTL of 62 (not 63) — one extra hop compared to reaching `L4` directly, consistent with the packet also crossing the L3VNI from `L4`'s VRF to `L1` to reach `H-202-22-7-L1`.

**Note:** this IOS-XE/IOL image does not support "downstream" static VRF leaking (`ip route <prefix> <mask> vrf <name> <next-hop>` to route from the global table into a VRF) — confirmed directly via context help (`ip route <prefix> <mask> ?` lists no `vrf` option). That ruled out leaking a global-table `EXT` link into `customer-b`, which is why the interface-membership + eBGP design above was used instead.

**Note:** host-to-host traffic works cleanly in both directions — `HE` → `customer-b` host (above) and `H-200-20-7-L3` → `HE` (`172.16.0.11`, 0% loss) both confirmed. The one thing that doesn't work is a ping *sourced from the router itself*: `ping vrf customer-b 172.16.0.11` run directly on `L4` fails, with `EXT` sending `ICMP unreachable` despite a valid route and no ACLs in the way. Not yet root-caused, but since every actual host path works, this looks like a router-local source-address quirk rather than a routing or fabric problem.

**customer-a:** not built. The same recipe applies — give `EXT` a third interface (or a sub-interface) into `customer-a`'s VRF, add a matching `vrf definition customer-a` on `EXT`, and set up a second eBGP session in that VRF between `EXT` and whichever leaf carries it.
