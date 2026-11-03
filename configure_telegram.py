"""Hidden interactive token input. --stdin is intended for local setup tools."""
from getpass import getpass
import argparse
import sys
from token_store import save_token

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdin", action="store_true")
    args = parser.parse_args()
    value = sys.stdin.read().strip() if args.stdin else getpass("Telegram bot token (hidden): ")
    save_token(value)
    print("Token saved with Windows DPAPI in ignored .runtime directory")
