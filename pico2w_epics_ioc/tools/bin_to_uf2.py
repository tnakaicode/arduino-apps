#!/usr/bin/env python3
"""Convert a raw BIN firmware image to UF2 blocks.

Default settings are for Pico 2 W (RP2350 ARM secure image in XIP flash).
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path


UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID_PRESENT = 0x00002000

# From pico-sdk boot/uf2.h
RP2350_ARM_S_FAMILY_ID = 0xE48BFF59

PAYLOAD_SIZE = 256
BLOCK_SIZE = 512


def convert_bin_to_uf2(input_path: Path, output_path: Path, base_addr: int, family_id: int) -> None:
    data = input_path.read_bytes()
    total_blocks = max(1, math.ceil(len(data) / PAYLOAD_SIZE))

    with output_path.open("wb") as f:
        for block_no in range(total_blocks):
            offset = block_no * PAYLOAD_SIZE
            payload = data[offset : offset + PAYLOAD_SIZE]
            if len(payload) < PAYLOAD_SIZE:
                payload = payload + b"\x00" * (PAYLOAD_SIZE - len(payload))

            header = struct.pack(
                "<IIIIIIII",
                UF2_MAGIC_START0,
                UF2_MAGIC_START1,
                UF2_FLAG_FAMILY_ID_PRESENT,
                base_addr + offset,
                PAYLOAD_SIZE,
                block_no,
                total_blocks,
                family_id,
            )

            # 512-byte UF2 block: 32-byte header + 476-byte data area + 4-byte end magic.
            # We use 256-byte payload and zero-pad the rest of the data area.
            data_area = payload + (b"\x00" * (476 - PAYLOAD_SIZE))
            block = header + data_area + struct.pack("<I", UF2_MAGIC_END)
            if len(block) != BLOCK_SIZE:
                raise RuntimeError(f"UF2 block size mismatch: {len(block)}")
            f.write(block)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert BIN to UF2")
    parser.add_argument("input_bin", type=Path, help="Input .bin file")
    parser.add_argument("output_uf2", type=Path, help="Output .uf2 file")
    parser.add_argument(
        "--base-addr",
        type=lambda x: int(x, 0),
        default=0x10000000,
        help="Flash base address (default: 0x10000000)",
    )
    parser.add_argument(
        "--family-id",
        type=lambda x: int(x, 0),
        default=RP2350_ARM_S_FAMILY_ID,
        help="UF2 family ID (default: RP2350 ARM S)",
    )
    args = parser.parse_args()

    convert_bin_to_uf2(args.input_bin, args.output_uf2, args.base_addr, args.family_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
