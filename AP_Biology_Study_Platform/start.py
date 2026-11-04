"""Start the local-only AP Biology Study Studio and open it in a web browser."""
from __future__ import annotations

import socket
import threading
import time
import webbrowser
import sys

HOST = '127.0.0.1'
PORT = 8000
URL = f'http://{HOST}:{PORT}'


def open_when_ready():
    for _ in range(80):
        try:
            with socket.create_connection((HOST, PORT), timeout=0.35):
                webbrowser.open(URL)
                return
        except OSError:
            time.sleep(0.25)


def main():
    try:
        import uvicorn
    except ImportError:
        print('Dependencies not installed. See README.md or run start_mac.command / start_windows.bat.')
        sys.exit(1)
    print(f'AP Biology Study Studio: {URL}')
    print('Your work stays on this computer. Press Ctrl+C to stop the server.')
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run('main:app', host=HOST, port=PORT, log_level='warning')


if __name__ == '__main__':
    main()
