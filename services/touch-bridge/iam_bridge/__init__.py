"""IAM-OS touch bridge.

Reads touch frames from lidar-service over a Unix socket and re-broadcasts
them on a WebSocket as the frozen touch contract. See docs/touch-contract.md
and specs.md §4.2.
"""

__version__ = "0.1.0"
