"""Read all data from a BYD Battery Box (or the simulator) without Home Assistant.

Usage (from the repository root)::

    python scripts/client_test.py 192.168.16.254 --port 8080
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.byd_battery_box.bydboxclient import BydBoxClient  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--unit-id", type=int, default=1)
    args = parser.parse_args()

    client = BydBoxClient(args.host, args.port, args.unit_id, 30)
    try:
        await client.init_data()
        await client.update_bmu_status_data()
        await client.update_all_bms_status_data()
        await client.update_all_log_data()
    finally:
        client.close()

    for key, value in sorted(client.data.items()):
        print(f"{key} {value}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
