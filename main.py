import argparse
import asyncio
import signal
import sys
import os
import time
import subprocess

from settings import USB_STORAGE, SD_STORAGE, BLEAK_DEVICE
from scanner import run

def main():
    # Main logic of the program goes here
    print("Running the scanner!\nUSB storage: " + USB_STORAGE + "\nSD storage: " + SD_STORAGE + "\nBT device: " + BLEAK_DEVICE + "\n")

    os.environ["BLEAK_DEVICE"] = BLEAK_DEVICE

    try:
        asyncio.run(run(None, None)) # from scanner.py library!
    except KeyboardInterrupt:
        # Fallback (some platforms)
        print_summary()

if __name__ == "__main__":
    main()
