import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import requests
import webview
from pynput import keyboard
import json


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


def start_hotkey_bridge(window: webview.Window) -> None:
	pressed_ctrl: bool = False

	def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:
		nonlocal pressed_ctrl
		try:
			if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
				pressed_ctrl = True
				return
			k = getattr(key, 'char', None)
			if not k:
				return
			k = k.lower()
		except Exception:
			return

		key_str = ('ctrl+' + k) if pressed_ctrl else k
		# Build robust JS using JSON to safely embed key string
		js = (
			"(function(){var k=" + json.dumps(key_str) + ";"
			"var wrap=document.querySelector('[data-hk-wrap='+k+']');"
			"var btn=wrap?wrap.querySelector('button'):null;"
			"if(!btn){btn=document.querySelector('[title=\"HK:'+k+'\"]');}"
			"if(btn){btn.click(); return true;} return false;})()"
		)
		try:
			window.evaluate_js(js)
		except Exception:
			pass

	def on_release(key: keyboard.Key | keyboard.KeyCode) -> None:
		nonlocal pressed_ctrl
		if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
			pressed_ctrl = False

	listener = keyboard.Listener(on_press=on_press, on_release=on_release)
	listener.daemon = True
	listener.start()


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
		# Start hotkey bridge after the window is ready
		webview.start(start_hotkey_bridge, (window,))
	finally:
		if proc is not None and proc.poll() is None:
			try:
				proc.terminate()
			except Exception:
				pass


if __name__ == "__main__":
	main()
