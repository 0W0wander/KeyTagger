import os
import json
import streamlit as st
from PIL import Image

from keytagger.db import Database
from keytagger.scanner import scan_directory, list_media_files

st.set_page_config(page_title="KeyTagger", layout="wide")

# Styles: consistent card layout, chip-sized actions
st.markdown(
	"""
	<style>
	.block-container { padding-top: 0.75rem; }
	.card { position:relative; display:grid; grid-template-rows: 1fr auto 28px 28px; gap:6px; border:1px solid transparent; border-radius:8px; }
	.card.selected { outline:2px solid #2563eb; box-shadow:0 0 0 3px rgba(37,99,235,0.25); background:rgba(37,99,235,0.05); }
	.thumb-wrap { position:relative; overflow:hidden; }
	/* Ensure images render as block to avoid extra whitespace */
	.thumb-wrap img { display:block; }
	/* Anchor Streamlit's image fullscreen button inside the actual image container */
	[data-testid="stImage"] { position:relative; }
	[data-testid="StyledFullScreenButton"] { position:absolute !important; top:6px !important; right:6px !important; margin:0 !important; transform:none !important; z-index:2 !important; }
	.tag-chip { display:inline-block; padding:2px 8px; border-radius:12px; background-color: rgba(128,128,128,0.2); margin-right:6px; font-size:12px; line-height:16px; }
	.card-name { font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
	.tag-row { display:flex; align-items:center; gap:6px; overflow:hidden; }
	.actions { display:flex; align-items:center; gap:6px; }
	/* Make popover triggers look like chips and equal to tag size */
	div[data-testid="stPopover"], div[data-testid="stPopoverIcon"] { display:inline-block; }
	div[data-testid="stPopover"] > button, div[data-testid="stPopoverIcon"] > button { padding:2px 8px !important; border-radius:12px !important; background:rgba(128,128,128,0.2) !important; border:0 !important; font-size:12px !important; height:22px !important; line-height:16px !important; }
	/* Style action buttons inside card like chips */
	.card .actions :where(button) { padding:2px 8px !important; border-radius:12px !important; background:rgba(128,128,128,0.2) !important; border:0 !important; font-size:12px !important; height:22px !important; line-height:16px !important; }
	.card.selected .actions :where(button[aria-label="Selected"], button:has(span:contains("Selected"))) { background:#2563eb !important; color:#fff !important; }
	/* Selection highlighting using a sentinel on the card block */
	.card-sentinel { display:none; }
	/* Only style the stVerticalBlock whose immediate child element-container contains the sentinel */
	[data-testid="stVerticalBlock"]:has(> [data-testid="element-container"] .card-sentinel[data-selected="1"]) {
		outline:2px solid #2563eb; box-shadow:0 0 0 3px rgba(37,99,235,0.25); background:rgba(37,99,235,0.05); border-radius:8px;
	}
	</style>
	""",
	unsafe_allow_html=True,
)

st.title("KeyTagger")

CONFIG_PATH = os.path.join(".", "keytag_config.json")
SQUARE_THUMBS_DIR = os.path.join(".", "thumbnails_square")
THUMB_SIZE = 320

# Config helpers to preserve multiple settings in one file
def _load_config() -> dict:
	try:
		with open(CONFIG_PATH, "r", encoding="utf-8") as f:
			data = json.load(f)
			return data if isinstance(data, dict) else {}
	except Exception:
		return {}


def _save_config(data: dict) -> None:
	try:
		with open(CONFIG_PATH, "w", encoding="utf-8") as f:
			json.dump(data, f)
	except Exception:
		pass

# Handle selection via URL param to allow clicking images
try:
	select_param = st.query_params.get("select")
	if select_param:
		st.session_state["selected_media_id"] = int(str(select_param))
		# Clear the param so reloads don't re-select unexpectedly
		try:
			del st.query_params["select"]
		except Exception:
			pass

	# Handle hotkey application via query param: ?hotkey=x
	hotkey_param = st.query_params.get("hotkey")
	if hotkey_param:
		key = str(hotkey_param).lower()
		selected_id = st.session_state.get("selected_media_id")
		if selected_id and key in st.session_state.get("hotkeys", {}):
			tag_to_add = st.session_state["hotkeys"][key]
			if tag_to_add:
				try:
					db: Database = st.session_state["db"]
					db.add_media_tags(int(selected_id), [tag_to_add])
					st.toast(f"Added tag '{tag_to_add}' via hotkey '{key}'")
				except Exception:
					pass
		# Clear param after handling
		try:
			del st.query_params["hotkey"]
		except Exception:
			pass

	# Handle captured key return: ?captured=x
	captured_param = st.query_params.get("captured")
	if captured_param:
		k = str(captured_param).lower()
		st.session_state["hk_new_key"] = k
		st.session_state["capture_hotkey"] = False
		st.session_state["show_hotkey_settings"] = True
		try:
			del st.query_params["captured"]
		except Exception:
			pass

	# Handle capture key flow: ?capture_key=y will set next key pressed into session
	capture_flag = st.query_params.get("capture_key")
	if capture_flag:
		st.session_state["capture_hotkey"] = True
		try:
			del st.query_params["capture_key"]
		except Exception:
			pass
except Exception:
	pass


def load_last_root_dir() -> str | None:
	try:
		with open(CONFIG_PATH, "r", encoding="utf-8") as f:
			data = json.load(f)
			val = data.get("last_root_dir")
			return str(val) if val else None
	except Exception:
		return None


def save_last_root_dir(path: str) -> None:
	try:
		data = _load_config()
		data["last_root_dir"] = os.path.abspath(path)
		_save_config(data)
	except Exception:
		pass


def load_hotkeys() -> dict[str, str]:
	data = _load_config()
	hm = data.get("hotkeys") or {}
	return {str(k).lower(): str(v).strip().lower() for k, v in hm.items() if str(k)}


def save_hotkeys(hotkey_map: dict[str, str]) -> None:
	data = _load_config()
	data["hotkeys"] = {str(k).lower(): str(v).strip().lower() for k, v in (hotkey_map or {}).items() if str(k)}
	_save_config(data)

if "db" not in st.session_state:
	st.session_state["db"] = Database(base_dir=".")

db: Database = st.session_state["db"]

# Selection state
if "selected_media_id" not in st.session_state:
	st.session_state["selected_media_id"] = None

# Hotkey map state
if "hotkeys" not in st.session_state:
	st.session_state["hotkeys"] = load_hotkeys()


def pick_folder(initial: str | None = None) -> str | None:
	try:
		import tkinter as tk
		from tkinter import filedialog
		root = tk.Tk()
		root.withdraw()
		root.wm_attributes("-topmost", 1)
		path = filedialog.askdirectory(initialdir=initial or os.path.abspath("."), title="Select folder to scan")
		root.destroy()
		return path or None
	except Exception:
		return None


@st.cache_data(show_spinner=False)
def build_square_thumbnail(src_path: str, size: int = THUMB_SIZE) -> str | None:
	"""Create a square, letterboxed thumbnail file and return its path."""
	if not src_path or not os.path.exists(src_path):
		return None
	os.makedirs(SQUARE_THUMBS_DIR, exist_ok=True)
	# Derive a deterministic filename based on original name
	base = os.path.splitext(os.path.basename(src_path))[0]
	dest = os.path.join(SQUARE_THUMBS_DIR, f"{base}_sq.jpg")
	if os.path.exists(dest):
		return dest
	try:
		with Image.open(src_path) as im:
			im = im.convert("RGB")
			w, h = im.size
			scale = min(size / max(w, 1), size / max(h, 1))
			new_w = max(1, int(w * scale))
			new_h = max(1, int(h * scale))
			resized = im.resize((new_w, new_h), Image.LANCZOS)
			canvas = Image.new("RGB", (size, size), color=(0, 0, 0))
			offset = ((size - new_w) // 2, (size - new_h) // 2)
			canvas.paste(resized, offset)
			canvas.save(dest, format="JPEG", quality=85)
			return dest
	except Exception:
		return None


with st.sidebar:
	st.header("Scan Settings")
	root_default = os.path.abspath(load_last_root_dir() or ".")
	if "scan_root_dir" not in st.session_state:
		st.session_state["scan_root_dir"] = root_default
	if "auto_scan_enabled" not in st.session_state:
		st.session_state["auto_scan_enabled"] = True
	if "auto_scan_pending" not in st.session_state:
		st.session_state["auto_scan_pending"] = True
	if "prev_root" not in st.session_state:
		st.session_state["prev_root"] = st.session_state["scan_root_dir"]

	if st.button("Pick Folder"):
		picked = pick_folder(st.session_state.get("scan_root_dir", root_default))
		if picked:
			st.session_state["scan_root_dir"] = picked
			save_last_root_dir(picked)
			st.session_state["auto_scan_pending"] = True
	root = st.text_input("Folder to scan", key="scan_root_dir")
	# Detect root changes
	if st.session_state["prev_root"] != st.session_state["scan_root_dir"]:
		st.session_state["prev_root"] = st.session_state["scan_root_dir"]
		save_last_root_dir(st.session_state["scan_root_dir"])
		st.session_state["auto_scan_pending"] = True

	st.checkbox("Auto-scan on open", key="auto_scan_enabled")
	left, right = st.columns([1, 1])
	with left:
		if st.button("Scan Folder", type="primary"):
			st.session_state["trigger_scan"] = True
	with right:
		if st.button("Add Hotkey Setting"):
			st.session_state["show_hotkey_settings"] = True
			st.session_state["capture_hotkey"] = True
	st.divider()
	st.header("Filters")
	search = st.text_input("Search filename contains")
	req_tags_csv = st.text_input("Required tags (comma-separated)")
	required_tags = [t.strip().lower() for t in req_tags_csv.split(",") if t.strip()] if req_tags_csv else []
	limit = st.slider("Results per page", min_value=20, max_value=400, value=100, step=20)
	offset = st.number_input("Page offset", min_value=0, value=0, step=1)

# Scan trigger and spinner progress
should_scan = st.session_state.get("trigger_scan") or (
	st.session_state.get("auto_scan_enabled") and st.session_state.get("auto_scan_pending")
)
if should_scan:
	files = list_media_files(st.session_state["scan_root_dir"]) if os.path.isdir(st.session_state["scan_root_dir"]) else []
	progress_text = st.empty()
	with st.spinner("Scanning..."):
		def on_progress(current: int, total: int, path: str) -> None:
			progress_text.text(f"Scanning {current}/{total}")
		result = scan_directory(st.session_state["scan_root_dir"], db, on_progress=on_progress)
	progress_text.text(f"Done: {result.scanned}/{len(files)} (updated {result.added_or_updated}, errors {result.errors})")
	st.session_state["trigger_scan"] = False
	st.session_state["auto_scan_pending"] = False

# Filter by current root so switching folders shows relevant items only
current_root = os.path.abspath(st.session_state["scan_root_dir"]) if st.session_state.get("scan_root_dir") else None
try:
	records, total = db.query_media(required_tags=required_tags, search_text=search, limit=limit, offset=offset, root_dir=current_root)
except TypeError:
	# Fallback when running with an older db.py signature
	records, total = db.query_media(required_tags=required_tags, search_text=search, limit=limit, offset=offset)
	if current_root:
		records = [r for r in records if os.path.abspath(r.root_dir) == current_root]
		total = len(records)

st.caption(f"Total matching: {total}")

cols_per_row = 6

# Render cards in strict rows so alignment is even
for start in range(0, len(records), cols_per_row):
	row_records = records[start:start + cols_per_row]
	row_cols = st.columns(cols_per_row)
	for j, rec in enumerate(row_records):
		with row_cols[j]:
			is_selected = st.session_state.get("selected_media_id") == rec.id
			card = st.container()
			with card:
				st.markdown(f"<span class='card-sentinel' data-selected=\"{'1' if is_selected else '0'}\"></span>", unsafe_allow_html=True)
				# Use square thumbnail to ensure uniform size
				sq = build_square_thumbnail(rec.thumbnail_path) if rec.thumbnail_path else None
				if sq and os.path.exists(sq):
					st.image(sq, use_column_width=True)
				elif rec.thumbnail_path and os.path.exists(rec.thumbnail_path):
					st.image(rec.thumbnail_path, use_column_width=True)
				else:
					st.empty()

				# Filename
				st.markdown(f"<div class='card-name'>{rec.file_name}</div>", unsafe_allow_html=True)

				# Tags row with chip-sized add button inline
				current_tags = db.get_media_tags(rec.id)
				chips_html = "".join([f"<span class='tag-chip'>{t}</span>" for t in current_tags]) if current_tags else "<span class='tag-chip'>(none)</span>"
				st.markdown(f"<div class='tag-row'>{chips_html}", unsafe_allow_html=True)
				with st.popover("+"):
					new_tag = st.text_input("New tag", key=f"newtag_{rec.id}")
					if st.button("Add", key=f"addbtn_{rec.id}"):
						new_tag_norm = (new_tag or "").strip().lower()
						if new_tag_norm:
							db.add_media_tags(rec.id, [new_tag_norm])
							st.toast("Tag added")
							st.rerun()
				st.markdown("</div>", unsafe_allow_html=True)

				# Actions row: Select and View chips
				st.markdown("<div class='actions'>", unsafe_allow_html=True)
				label = "Selected" if is_selected else "Select"
				if st.button(label, key=f"select_{rec.id}"):
					st.session_state["selected_media_id"] = None if is_selected else rec.id
					st.rerun()
				with st.popover("View"):
					if rec.file_path and os.path.exists(rec.file_path):
						st.image(rec.file_path, use_column_width=True)
					elif rec.thumbnail_path and os.path.exists(rec.thumbnail_path):
						st.image(rec.thumbnail_path, use_column_width=True)
				st.markdown("</div>", unsafe_allow_html=True)
				# end actions
				# end card container

# Global key listener: map defined keys to query param change
# Use a tiny script to push ?hotkey=<key> without full page reload
if st.session_state.get("hotkeys"):
	keys_list = sorted(list(st.session_state["hotkeys"].keys()))
	keys_json = json.dumps(keys_list)
	listener_html = f"""
	<script>
	(function() {{
	  const ALLOWED = new Set({keys_json});
	  if (window.__keytagger_keys_installed) return;
	  window.__keytagger_keys_installed = true;
	  window.addEventListener('keydown', function(e) {{
	    if (e.target && ['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
	    if (e.ctrlKey || e.metaKey || e.altKey) return;
	    const k = (e.key || '').toLowerCase();
	    if (window.__capture_next_key) return; // let capture handler handle it
	    if (!ALLOWED.has(k)) return;
	    try {{
	      const url = new URL(window.location.href);
	      url.searchParams.set('hotkey', k);
	      window.location.assign(url.toString());
	    }} catch (_) {{}}
	  }}, true);
	}})();
	</script>
	"""
	st.markdown(listener_html, unsafe_allow_html=True)

# Install capture listener when capture mode is active
if st.session_state.get("capture_hotkey"):
	capture_html = """
	<script>
	(function(){
	  if (window.__keytagger_capture_installed) return;
	  window.__keytagger_capture_installed = true;
	  window.__capture_next_key = true;
	  function __kt_handleCapture(e){
	    if (e.target && ['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
	    if (e.ctrlKey || e.metaKey || e.altKey) return;
	    const k = (e.key || '').toLowerCase();
	    e.preventDefault();
	    window.__capture_next_key = false;
	    window.removeEventListener('keydown', __kt_handleCapture, true);
	    try {
	      const url = new URL(window.location.href);
	      url.searchParams.set('captured', k);
	      window.location.assign(url.toString());
	    } catch(_) {}
	  }
	  window.addEventListener('keydown', __kt_handleCapture, true);
	})();
	</script>
	"""
	st.markdown(capture_html, unsafe_allow_html=True)

# Hotkey Settings modal
show_modal = st.session_state.get("show_hotkey_settings")
if show_modal:
	st.markdown("<div class='modal-backdrop'></div>", unsafe_allow_html=True)
	st.markdown("<div class='modal-panel'>", unsafe_allow_html=True)
	st.subheader("Hotkey Settings")
	st.caption("Assign single keys (a-z, 0-9, punctuation) to tags. When pressed, the tag is added to the selected image.")

	# Existing mappings table
	hotkeys = dict(st.session_state.get("hotkeys", {}))
	if hotkeys:
		for k in sorted(hotkeys.keys()):
			c1, c2, c3 = st.columns([1, 3, 1])
			with c1:
				st.text_input("Key", value=k, key=f"hk_key_{k}", disabled=True)
			with c2:
				new_tag_val = st.text_input("Tag", value=hotkeys[k], key=f"hk_tag_{k}")
				if new_tag_val.strip().lower() != hotkeys[k]:
					hotkeys[k] = new_tag_val.strip().lower()
			with c3:
				if st.button("Remove", key=f"hk_remove_{k}"):
					hotkeys.pop(k, None)
	else:
		st.info("No hotkeys defined yet.")

	st.markdown("---")
	st.markdown("Add new mapping")
	c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
	with c1:
		capture_on = bool(st.session_state.get("capture_hotkey"))
		label = "Press any key..." if capture_on else "Capture key"
		if st.button(label, key="hk_capture_btn"):
			st.session_state["capture_hotkey"] = True
			# install a capture script
			st.session_state["_install_capture_script"] = True
			st.rerun()
	with c2:
		new_key = st.text_input("Key", key="hk_new_key", disabled=True)
	with c3:
		new_tag = st.text_input("Tag", key="hk_new_tag")
	with c4:
		if st.button("Add", key="hk_add_btn"):
			k = (st.session_state.get("hk_new_key") or "").strip().lower()
			t = (new_tag or "").strip().lower()
			if k and len(k) == 1 and t:
				hotkeys[k] = t
				st.session_state["hotkeys"] = hotkeys
				save_hotkeys(hotkeys)
				st.session_state["hk_new_key"] = ""
				st.session_state["hk_new_tag"] = ""
				st.toast("Hotkey added")
				st.rerun()

	# Footer buttons
	f1, f2 = st.columns([1, 1])
	with f1:
		if st.button("Save changes", key="hk_save"):
			# Collect edited tags for existing keys
			updated = {}
			for key in list(hotkeys.keys()):
				val = st.session_state.get(f"hk_tag_{key}") or hotkeys[key]
				val = str(val).strip().lower()
				if val:
					updated[str(key).lower()] = val
			st.session_state["hotkeys"] = updated
			save_hotkeys(updated)
			st.toast("Saved hotkeys")
			st.session_state["show_hotkey_settings"] = False
			st.rerun()
	with f2:
		if st.button("Close", key="hk_close"):
			st.session_state["show_hotkey_settings"] = False
			st.rerun()

	st.markdown("</div>", unsafe_allow_html=True)
