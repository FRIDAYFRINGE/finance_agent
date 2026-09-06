"""Convenience launcher CLI for the Financial Analyst AI Agent Dual Interface.

Usage:
    python run.py api       # Starts FastAPI REST server on port 8000
    python run.py ui        # Starts Streamlit Web UI on port 8501
    python run.py both      # Starts both FastAPI and Streamlit concurrently
"""

import os
import signal
import subprocess
import sys
import time


def run_api():
    """Runs the FastAPI service via Uvicorn."""
    print("=" * 60)
    print("🚀 Starting FastAPI REST API on http://127.0.0.1:8000")
    print("📖 Interactive Swagger Documentation: http://127.0.0.1:8000/docs")
    print("=" * 60)
    cmd = [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    return subprocess.run(cmd)


def run_ui():
    """Runs the Streamlit Web Application."""
    print("=" * 60)
    print("🖥️ Starting Streamlit Web Interface on http://127.0.0.1:8501")
    print("=" * 60)
    cmd = [sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501"]
    return subprocess.run(cmd)


def run_both():
    """Starts both FastAPI and Streamlit concurrently and handles graceful teardown."""
    print("=" * 60)
    print("🚀 Starting Dual Interface (FastAPI on :8000 + Streamlit on :8501)...")
    print("=" * 60)

    api_cmd = [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ui_cmd = [sys.executable, "-m", "streamlit", "run", "ui/app.py", "--server.port", "8501"]

    api_proc = subprocess.Popen(api_cmd)
    time.sleep(1.5)  # Allow API server to initialize
    ui_proc = subprocess.Popen(ui_cmd)

    try:
        # Wait for either process to exit
        while True:
            api_status = api_proc.poll()
            ui_status = ui_proc.poll()

            if api_status is not None:
                print(f"FastAPI process exited with code {api_status}. Terminating Streamlit...")
                break
            if ui_status is not None:
                print(f"Streamlit process exited with code {ui_status}. Terminating FastAPI...")
                break

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        for proc, name in [(api_proc, "FastAPI"), (ui_proc, "Streamlit")]:
            if proc.poll() is None:
                print(f"Terminating {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "both"

    if mode == "api":
        run_api()
    elif mode == "ui":
        run_ui()
    elif mode in ("both", "all"):
        run_both()
    else:
        print(f"❌ Unknown mode: '{mode}'. Valid modes are: 'api', 'ui', or 'both'.")
        print("Example: python run.py both")
        sys.exit(1)


if __name__ == "__main__":
    main()
