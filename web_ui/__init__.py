"""
Web UI module for SAR Scanner.

This module starts the FastAPI web server that provides:
- Real-time dashboard with live data
- GPS and scanner status indicators
- Filtered data tables
- Interactive heatmap overlay
"""

import threading
import subprocess
import sys
import os
import time

def start_web_ui():
    """
    Start the web UI server in a background thread.
    
    Returns:
        tuple: (thread, process) or (None, None) if failed
    """
    
    web_dir = os.path.dirname(os.path.abspath(__file__))
    app_file = os.path.join(web_dir, "app.py")
    
    def run_server():
        """Run the FastAPI server."""
        try:
            # Import uvicorn here to avoid issues if FastAPI is not installed
            import uvicorn
            from app import app, update_scanner_state
            
            # Update scanner state from settings
            from settings import SCAN_MODE
            update_scanner_state(SCAN_MODE, False)  # WiFi monitor mode will be updated by wifi_scanner
            
            uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
        except ImportError:
            print("Error: FastAPI or uvicorn not installed. Install with:")
            print("  pip install fastapi uvicorn")
        except Exception as e:
            print(f"Error starting web UI: {e}", file=sys.stderr)
    
    thread = threading.Thread(target=run_server, daemon=True, name="web-ui-server")
    thread.start()
    
    return thread


if __name__ == "__main__":
    start_web_ui()
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down web UI...")
