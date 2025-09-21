import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import requests
import webview


APP_FILE = "app.py"
STARTUP_TIMEOUT_SECONDS = 30


def is_frozen() -> bool:
	return getattr(sys, "frozen", False)


def base_dir() -> str:
	# When frozen, resources (added via --add-data) reside in sys._MEIPASS
	return getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))


def find_free_port() -> int:
	with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
		s.bind(("127.0.0.1", 0))
		return s.getsockname()[1]


def wait_for_streamlit(url: str, timeout_seconds: int = STARTUP_TIMEOUT_SECONDS) -> bool:
	deadline = time.time() + timeout_seconds
	healthz = url.rstrip("/") + "/healthz"
	while time.time() < deadline:
		try:
			resp = requests.get(healthz, timeout=1)
			if resp.status_code == 200:
				return True
		except requests.RequestException:
			pass
		time.sleep(0.2)
	return False


def start_streamlit_embedded(port: int) -> None:
	# Start Streamlit in-process (works in PyInstaller bundle)
	from streamlit.web import cli as stcli  # type: ignore
	app_path = os.path.join(base_dir(), APP_FILE)
	os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
	os.environ.setdefault("BROWSER", "none")
	# Configure argv for stcli
	sys.argv = [
		"streamlit",
		"run",
		app_path,
		"--server.port",
		str(port),
		"--server.headless",
		"true",
		"--browser.gatherUsageStats",
		"false",
	]
	# Run in a thread so we can open the window
	import threading

	thread = threading.Thread(target=stcli.main, daemon=True)
	thread.start()


def start_streamlit_subprocess(port: int) -> subprocess.Popen:
	# Dev mode: spawn separate process using system Python
	env = os.environ.copy()
	env.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
	cmd = [
		sys.executable,
		"-m",
		"streamlit",
		"run",
		APP_FILE,
		"--server.port",
		str(port),
		"--server.headless",
		"true",
		"--browser.gatherUsageStats",
		"false",
	]
	proc = subprocess.Popen(
		cmd,
		env=env,
		stdin=subprocess.DEVNULL,
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		text=True,
	)
	return proc


def main() -> None:
	port = int(os.environ.get("KEYTAGGER_PORT", os.environ.get("KEYTAG_PORT", str(find_free_port()))))
	url = f"http://127.0.0.1:{port}"

	proc: subprocess.Popen | None = None
	try:
		if is_frozen():
			start_streamlit_embedded(port)
		else:
			proc = start_streamlit_subprocess(port)

		ready = wait_for_streamlit(url)
		if not ready:
			raise RuntimeError("Streamlit did not start in time")

		window = webview.create_window("KeyTagger – Media Tagger", url, width=1200, height=800, resizable=True)
		webview.start()
	finally:
		if proc is not None and proc.poll() is None:
			try:
				proc.terminate()
			except Exception:
				pass


if __name__ == "__main__":
	main()
