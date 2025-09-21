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
	.card { display:grid; grid-template-rows: 1fr auto 28px 28px; gap:6px; }
	.tag-chip { display:inline-block; padding:2px 8px; border-radius:12px; background-color: rgba(128,128,128,0.2); margin-right:6px; font-size:12px; line-height:16px; }
	.card-name { font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
	.tag-row { display:flex; align-items:center; gap:6px; overflow:hidden; }
	.actions { display:flex; align-items:center; gap:6px; }
	/* Make popover triggers look like chips and equal to tag size */
	div[data-testid="stPopover"], div[data-testid="stPopoverIcon"] { display:inline-block; }
	div[data-testid="stPopover"] > button, div[data-testid="stPopoverIcon"] > button { padding:2px 8px !important; border-radius:12px !important; background:rgba(128,128,128,0.2) !important; border:0 !important; font-size:12px !important; height:22px !important; line-height:16px !important; }
	</style>
	""",
	unsafe_allow_html=True,
)

st.title("KeyTagger")

CONFIG_PATH = os.path.join(".", "keytag_config.json")
SQUARE_THUMBS_DIR = os.path.join(".", "thumbnails_square")
THUMB_SIZE = 320


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
		with open(CONFIG_PATH, "w", encoding="utf-8") as f:
			json.dump({"last_root_dir": os.path.abspath(path)}, f)
	except Exception:
		pass

if "db" not in st.session_state:
	st.session_state["db"] = Database(base_dir=".")

db: Database = st.session_state["db"]


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

	st.checkbox("Auto-scan on open", value=st.session_state["auto_scan_enabled"], key="auto_scan_enabled")
	if st.button("Scan Folder", type="primary"):
		st.session_state["trigger_scan"] = True
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

records, total = db.query_media(required_tags=required_tags, search_text=search, limit=limit, offset=offset)

st.caption(f"Total matching: {total}")

cols_per_row = 6

# Render cards in strict rows so alignment is even
for start in range(0, len(records), cols_per_row):
	row_records = records[start:start + cols_per_row]
	row_cols = st.columns(cols_per_row)
	for j, rec in enumerate(row_records):
		with row_cols[j]:
			st.markdown("<div class='card'>", unsafe_allow_html=True)
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

			# Actions row: View chip aligned across cards
			st.markdown("<div class='actions'>", unsafe_allow_html=True)
			with st.popover("View"):
				if rec.file_path and os.path.exists(rec.file_path):
					st.image(rec.file_path, use_column_width=True)
				elif rec.thumbnail_path and os.path.exists(rec.thumbnail_path):
					st.image(rec.thumbnail_path, use_column_width=True)
			st.markdown("</div>", unsafe_allow_html=True)

			st.markdown("</div>", unsafe_allow_html=True)
