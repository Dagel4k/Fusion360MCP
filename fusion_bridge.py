import sys
import json
import urllib.request
import threading
import queue
from urllib.parse import urljoin

# Pure MCP SSE-to-stdio Proxy Bridge
# This script forwards everything between Claude Desktop (stdio) and the Fusion 360 MCP server (SSE).
# It doesn't define any tools itself, so it exposes exactly what the Fusion server provides.
# This prevents asyncio conflicts and ensures all server tools are visible.

def main():
    url = "http://127.0.0.1:3000/sse"
    post_url_queue = queue.Queue()
    
    print(f"Connecting to {url}...", file=sys.stderr)
    
    def stdio_to_server():
        """Read from STDIN and POST to the dynamically discovered session URL."""
        try:
            # Wait for the endpoint URL to be discovered from the SSE stream
            post_url = post_url_queue.get(timeout=15)
            print(f"Session endpoint discovered: {post_url}", file=sys.stderr)
        except queue.Empty:
            print("Error: No endpoint URL discovered from SSE stream.", file=sys.stderr)
            return

        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                # Forward JSON-RPC message to the server
                req = urllib.request.Request(
                    post_url, 
                    data=line.encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        # We don't need to read the response if it's just an ACK
                        pass 
                except Exception as e:
                    print(f"Error posting message: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Unexpected error in stdio_to_server: {e}", file=sys.stderr)

    try:
        # Start the sender thread
        sender_thread = threading.Thread(target=stdio_to_server, daemon=True)
        sender_thread.start()

        # Connect to the SSE stream
        with urllib.request.urlopen(url, timeout=None) as response:
            print("Connected to SSE stream.", file=sys.stderr)
            while True:
                line = response.readline()
                if not line:
                    print("Connection closed by server.", file=sys.stderr)
                    break
                
                decoded_line = line.decode('utf-8').strip()
                
                # Handle endpoint event: 'event: endpoint' followed by 'data: URL'
                if decoded_line.startswith('event: endpoint'):
                    data_line = response.readline().decode('utf-8').strip()
                    if data_line.startswith('data: '):
                        endpoint = data_line[6:]
                        full_endpoint = urljoin(url, endpoint)
                        post_url_queue.put(full_endpoint)
                
                # Handle actual data events
                elif decoded_line.startswith('data: '):
                    data = decoded_line[6:]
                    # Write the raw JSON-RPC message to STDOUT
                    print(data, flush=True)
                    
    except Exception as e:
        print(f"Bridge connection error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
