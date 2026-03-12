"""
To run me enter below into terminal
python -m archilume --debug

"""

# archilume/archilume/__main__.py
import argparse
import socket

# 1. IMPORT the app, do not define it here!
from archilume.apps.dash_app import app 

def get_free_port(start_port, max_port=8100):
    """Scans for an available port starting from start_port."""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # connect_ex returns 0 if the port is open/occupied
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError(f"No free ports found between {start_port} and {max_port}.")

def main():
    # Set up command-line arguments
    parser = argparse.ArgumentParser(description="Launch the Archilume Dashboard")
    parser.add_argument("--port", type=int, default=8050, help="Target port (default: 8050)")
    parser.add_argument("--debug", action="store_true", help="Launch in debug mode")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host IP address")
    args = parser.parse_args()

    # Automatically find an open port, falling back if the default is taken
    final_port = get_free_port(args.port)
    
    if final_port != args.port:
        print(f"Port {args.port} is in use. Falling back to available port: {final_port}")
    else:
        print(f"Starting Archilume on port {final_port}...")

    # Start the server
    app.run(
        host=args.host,
        port=final_port,
        debug=args.debug
    )

if __name__ == "__main__":
    main()