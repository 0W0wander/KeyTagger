import os
import json
import threading
from typing import Dict, List, Optional, Set, Tuple
import sys
import time
import subprocess
import shutil
import signal
import atexit

from PIL import Image, ImageTk
try:
    from PIL import ImageDraw, ImageFont
except Exception:
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

from keytagger.db import Database, MediaRecord
from keytagger.scanner import scan_directory, list_media_files

CONFIG_PATH = os.path.join('.', 'keytag_config.json')
THUMBS_DIR = os.path.join('.', 'thumbnails_square')
THUMB_SIZE = 320


def load_config() -> Dict:
	try:
		with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
			data = json.load(f)
			return data if isinstance(data, dict) else {}
	except Exception:
		return {}


def save_config(data: Dict) -> None:
	try:
		with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
			json.dump(data, f)
	except Exception:
		pass


def load_hotkeys() -> Dict[str, str]:
	cfg = load_config()
	hk = cfg.get('hotkeys') or {}
	return {str(k).lower(): str(v).strip().lower() for k, v in hk.items() if str(k)}


def save_hotkeys(hotkeys: Dict[str, str]) -> None:
	cfg = load_config()
	cfg['hotkeys'] = {str(k).lower(): str(v).strip().lower() for k, v in (hotkeys or {}).items()}
	save_config(cfg)


def get_tagging_nav_keys() -> Tuple[str, str]:
	cfg = load_config()
	prev_k = str(cfg.get('tagging_prev_key') or 'a').lower()
	next_k = str(cfg.get('tagging_next_key') or 'd').lower()
	return prev_k, next_k


def set_tagging_nav_keys(prev_key: str, next_key: str) -> None:
	cfg = load_config()
	cfg['tagging_prev_key'] = (prev_key or '').strip().lower() or 'a'
	cfg['tagging_next_key'] = (next_key or '').strip().lower() or 'd'
	save_config(cfg)


def get_thumb_size() -> int:
	cfg = load_config()
	val = cfg.get('thumb_size')
	try:
		return int(val)
	except Exception:
		return THUMB_SIZE


def set_thumb_size(px: int) -> None:
	cfg = load_config()
	cfg['thumb_size'] = int(px)
	save_config(cfg)


def get_dark_mode() -> bool:
	cfg = load_config()
	val = cfg.get('dark_mode')
	return bool(val) if isinstance(val, (bool, int)) else False


def set_dark_mode(enabled: bool) -> None:
	cfg = load_config()
	cfg['dark_mode'] = bool(enabled)
	save_config(cfg)


def get_last_root_dir() -> Optional[str]:
	cfg = load_config()
	val = cfg.get('last_root_dir')
	return str(val) if val else None


def set_last_root_dir(path: str) -> None:
	cfg = load_config()
	cfg['last_root_dir'] = os.path.abspath(path)
	save_config(cfg)


def build_square_thumbnail(src_path: str, size: int = THUMB_SIZE) -> Optional[str]:
	if not src_path or not os.path.exists(src_path):
		return None
	os.makedirs(THUMBS_DIR, exist_ok=True)
	base = os.path.splitext(os.path.basename(src_path))[0]
	dest = os.path.join(THUMBS_DIR, f"{base}_sq.jpg")
	if os.path.exists(dest):
		return dest
	try:
		with Image.open(src_path) as im:
			im = im.convert('RGB')
			w, h = im.size
			scale = min(size / max(w, 1), size / max(h, 1))
			new_w = max(1, int(w * scale))
			new_h = max(1, int(h * scale))
			resized = im.resize((new_w, new_h), Image.LANCZOS)
			canvas = Image.new('RGB', (size, size), color=(0, 0, 0))
			offset = ((size - new_w) // 2, (size - new_h) // 2)
			canvas.paste(resized, offset)
			canvas.save(dest, format='JPEG', quality=85)
			return dest
	except Exception:
		return None


def build_audio_placeholder(size: int = THUMB_SIZE) -> Optional[str]:
	"""Create or return a cached grey square placeholder with centered 'audio' text."""
	try:
		os.makedirs(THUMBS_DIR, exist_ok=True)
		dest = os.path.join(THUMBS_DIR, f"audio_placeholder_v3_{int(size)}.jpg")
		if os.path.exists(dest):
			return dest
		# Dark background for strong contrast; readable in light/dark themes
		bg = (31, 41, 55)
		fg = (229, 231, 235)
		img = Image.new('RGB', (int(size), int(size)), color=bg)
		if ImageDraw is not None:
			draw = ImageDraw.Draw(img)
			text = 'audio'
			# Try to pick a reasonable font size relative to square size
			try:
				# Use a default bitmap font when truetype not available
				font_size = max(16, int(size * 0.2))
				font = ImageFont.load_default() if ImageFont is not None else None
				# Measure text bounding box for centering
				bbox = draw.textbbox((0, 0), text, font=font)
				tw = (bbox[2] - bbox[0]) if bbox else 0
				th = (bbox[3] - bbox[1]) if bbox else 0
				x = (size - tw) // 2
				y = (size - th) // 2
				draw.text((x, y), text, fill=fg, font=font)
			except Exception:
				# Fallback: simple text without font metrics
				draw.text((size // 3, size // 3), text, fill=fg)
		img.save(dest, format='JPEG', quality=85)
		return dest
	except Exception:
		return None


class KeyTaggerApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title('KeyTagger – Desktop')
		self.dark_mode: bool = get_dark_mode()
		self.palette: Dict[str, str] = {}
		self._setup_theme()
		self.db = Database(base_dir='.')
		self.hotkeys: Dict[str, str] = load_hotkeys()
		self.selected_ids: Set[int] = set()
		self._selection_anchor_id: Optional[int] = None
		self.photo_cache: Dict[int, ImageTk.PhotoImage] = {}
		self.records: List[MediaRecord] = []
		self.card_frames: List[ttk.Frame] = []
		self._cols: int = 1
		self._thumb_px: int = max(120, int(get_thumb_size()))
		self._thumb_apply_after_id: Optional[str] = None
		# Viewing mode state
		self.view_mode: bool = False
		self.current_view_id: Optional[int] = None
		self.viewer_photo: Optional[ImageTk.PhotoImage] = None
		self.force_cols: Optional[int] = None
		self.gallery_height: Optional[int] = None
		# Tagging mode state
		self.tagging_mode: bool = False
		self.tag_prev_key, self.tag_next_key = get_tagging_nav_keys()
		self.tag_prev_key_var = tk.StringVar(value=self.tag_prev_key)
		self.tag_next_key_var = tk.StringVar(value=self.tag_next_key)
		self.tag_input_var = tk.StringVar()
		# Tag autocomplete state
		self._tag_suggest_window: Optional[tk.Toplevel] = None
		self._tag_suggest_list: Optional[tk.Listbox] = None
		self._tag_suggest_items: List[str] = []
		# Media playback state
		self._video_thread: Optional[threading.Thread] = None
		self._video_stop_event: Optional[threading.Event] = None
		self._video_path_playing: Optional[str] = None
		self._audio_proc: Optional[subprocess.Popen] = None
		self._video_pause: bool = False
		self._video_total_frames: int = 0
		self._video_fps: float = 0.0
		self._video_duration_s: float = 0.0
		self._video_current_frame: int = 0
		self._video_seek_to_frame: Optional[int] = None
		self._video_lock = threading.Lock()
		self._video_pos_var = tk.DoubleVar(value=0.0)
		self._video_updating_slider: bool = False
		self._video_clock_start: float = 0.0
		self._video_clock_offset: float = 0.0
		self._video_paused_at_media_sec: float = 0.0
		# Session token to avoid stale updates from previous media
		self._viewer_session: int = 0
		# Debounce id for gallery resize in viewing mode
		self._gallery_resize_after_id: Optional[str] = None
		# Track last canvas width to avoid redundant relayouts
		self._last_canvas_width: Optional[int] = None
		# Freeze gallery height in viewing mode to prevent thrash
		self._freeze_gallery_height: bool = False
		# Track what is currently rendered in the viewer to avoid redundant restarts
		self._viewer_current_id: Optional[int] = None
		self._viewer_current_type: Optional[str] = None
		# Close handler
		try:
			self.root.protocol('WM_DELETE_WINDOW', self._on_close)
		except Exception:
			pass
		# Ensure audio is stopped if the process exits unexpectedly
		try:
			atexit.register(lambda: self._terminate_audio_proc())
		except Exception:
			pass
		# GIF playback state
		self._gif_thread: Optional[threading.Thread] = None
		self._gif_stop_event: Optional[threading.Event] = None
		self._gif_path_playing: Optional[str] = None
		self._gif_pause: bool = False
		# Toast notification window (single-instance)
		self._toast_window: Optional[tk.Toplevel] = None

		self._build_ui()
		default_dir = get_last_root_dir() or os.path.abspath('.')
		self.folder_var.set(default_dir)
		self.refresh_records()
		self._bind_hotkeys()

	def _build_ui(self) -> None:
		self.root.geometry('1280x800')
		self.root.rowconfigure(0, weight=1)
		self.root.columnconfigure(1, weight=1)

		# Sidebar
		side = ttk.Frame(self.root, padding=12, style='Side.TFrame')
		side.grid(row=0, column=0, sticky='ns', rowspan=2)

		self.folder_var = tk.StringVar()
		title = ttk.Label(side, text='KeyTagger', style='Title.TLabel')
		title.pack(anchor='w', pady=(0, 8))
		folder_row = ttk.Frame(side, style='Side.TFrame')
		folder_row.pack(fill='x', pady=(0, 8))
		pick_btn = ttk.Button(folder_row, text='Pick Folder', command=self.pick_folder, style='Primary.TButton')
		pick_btn.pack(side='left')
		folder_entry = ttk.Entry(side, textvariable=self.folder_var, width=40)
		folder_entry.pack(fill='x', pady=(6, 8))
		scan_btn = ttk.Button(side, text='Scan Folder', command=self.scan_folder, style='Accent.TButton')
		scan_btn.pack(fill='x')

		# Tag filter (comma-separated). Default to OR behavior; a toggle switches to AND
		filter_lbl = ttk.Label(side, text='Filter by tags (comma-separated)', style='Muted.TLabel')
		filter_lbl.pack(anchor='w', pady=(10, 2))
		self.filter_tags_var = tk.StringVar()
		filter_entry = ttk.Entry(side, textvariable=self.filter_tags_var, width=40)
		filter_entry.pack(fill='x')
		self.filter_match_all_var = tk.BooleanVar(value=False)  # False = OR (default)
		chk_all = ttk.Checkbutton(side, text='Match ALL tags (AND)', variable=self.filter_match_all_var, command=self.apply_filters)
		chk_all.pack(anchor='w', pady=(4, 8))
		btn_apply_filter = ttk.Button(side, text='Apply Filter', command=self.apply_filters, style='Small.TButton')
		btn_apply_filter.pack(anchor='w')

		# Thumbnail size slider
		sz_label = ttk.Label(side, text='Thumbnail size', style='Muted.TLabel')
		sz_label.pack(anchor='w', pady=(10, 2))
		self.thumb_size_var = tk.IntVar(value=int(self._thumb_px))
		sz = ttk.Scale(side, from_=120, to=512, orient='horizontal', variable=self.thumb_size_var, command=self._on_thumb_size_change)
		sz.set(self._thumb_px)
		sz.pack(fill='x')

		# Hotkey settings
		settings_btn = ttk.Button(side, text='Settings', command=self.open_settings)
		settings_btn.pack(fill='x', pady=(12, 6))
		self.last_key_var = tk.StringVar(value='Last key: (none)')
		last_key_lbl = ttk.Label(side, textvariable=self.last_key_var, style='Muted.TLabel')
		last_key_lbl.pack(fill='x')

		# Hotkeys panel
		sep1 = ttk.Separator(side)
		sep1.pack(fill='x', pady=(10, 8))
		hk_title = ttk.Label(side, text='Tags & Hotkeys', style='Title.TLabel')
		hk_title.pack(anchor='w', pady=(0, 6))
		self.hk_new_key_var = tk.StringVar()
		self.hk_new_tag_var = tk.StringVar()
		row_add = ttk.Frame(side, style='Side.TFrame')
		row_add.pack(fill='x', pady=(0, 6))
		entry_key = ttk.Entry(row_add, textvariable=self.hk_new_key_var, width=8)
		entry_key.pack(side='left')
		entry_tag = ttk.Entry(row_add, textvariable=self.hk_new_tag_var, width=16)
		entry_tag.pack(side='left', padx=(6, 6))
		btn_add = ttk.Button(row_add, text='Add', command=self._add_hotkey_mapping, style='Small.TButton')
		btn_add.pack(side='left')
		self.hotkey_list_frame = ttk.Frame(side, style='Side.TFrame')
		self.hotkey_list_frame.pack(fill='x', pady=(6, 0))
		self._render_hotkey_list()

		# Viewing mode toggle button
		self.view_toggle_btn = ttk.Button(side, text='Enter Viewing Mode', command=self.toggle_view_mode, style='Small.TButton')
		self.view_toggle_btn.pack(fill='x', pady=(8, 0))
		# Tagging mode toggle button
		self.tagging_toggle_btn = ttk.Button(side, text='Enter Tagging Mode', command=self.toggle_tagging_mode, style='Small.TButton')
		self.tagging_toggle_btn.pack(fill='x', pady=(6, 0))
		# Tagging navigation hotkeys (visible only in tagging mode)
		self.tagging_nav_frame = ttk.Frame(side, style='Side.TFrame')
		row_nav1 = ttk.Frame(self.tagging_nav_frame, style='Side.TFrame')
		row_nav1.pack(fill='x', pady=(8, 2))
		lbl_prev = ttk.Label(row_nav1, text='Tagging: Prev key', style='Muted.TLabel')
		lbl_prev.pack(side='left')
		entry_prev = ttk.Entry(row_nav1, textvariable=self.tag_prev_key_var, width=8)
		entry_prev.pack(side='right')
		row_nav2 = ttk.Frame(self.tagging_nav_frame, style='Side.TFrame')
		row_nav2.pack(fill='x', pady=(0, 8))
		lbl_next = ttk.Label(row_nav2, text='Tagging: Next key', style='Muted.TLabel')
		lbl_next.pack(side='left')
		entry_next = ttk.Entry(row_nav2, textvariable=self.tag_next_key_var, width=8)
		entry_next.pack(side='right')
		btn_apply_nav = ttk.Button(self.tagging_nav_frame, text='Apply Tagging Keys', style='Small.TButton', command=self._apply_tagging_keys)
		btn_apply_nav.pack(fill='x')
		self.tagging_nav_frame.pack_forget()

		# Main area with scrollable canvas (gallery)
		main = ttk.Frame(self.root, style='App.TFrame')
		main.grid(row=0, column=1, sticky='nsew')
		main.rowconfigure(0, weight=1)
		main.columnconfigure(0, weight=1)

		self.canvas = tk.Canvas(main, highlightthickness=0, background=self.palette.get('canvas_bg', '#f6f7fb'))
		self.scroll_y = ttk.Scrollbar(main, orient='vertical', command=self.canvas.yview)
		self.scroll_x = ttk.Scrollbar(main, orient='horizontal', command=self.canvas.xview)
		self.grid_frame = ttk.Frame(self.canvas, style='App.TFrame')
		self.grid_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
		self.grid_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor='nw')
		self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
		self.canvas.grid(row=0, column=0, sticky='nsew')
		self.scroll_y.grid(row=0, column=1, sticky='ns')
		self.scroll_x.grid(row=1, column=0, sticky='ew')
		self.scroll_x.grid_remove()
		self.canvas.bind('<Configure>', self._on_canvas_configure)

		# Bottom viewer area (hidden until viewing mode)
		self.viewer_container = ttk.Frame(self.root, style='App.TFrame')
		self.viewer_container.grid(row=1, column=1, sticky='nsew')
		self.root.rowconfigure(1, weight=0)
		self.viewer_label = ttk.Label(self.viewer_container)
		self.viewer_label.grid(row=0, column=0, sticky='nsew', padx=8, pady=8)
		# Video controls (hidden unless a video is selected)
		self.video_controls = ttk.Frame(self.viewer_container, style='App.TFrame')
		self.video_controls.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 10))
		self.video_controls.columnconfigure(1, weight=1)
		self.video_play_btn = ttk.Button(self.video_controls, text='Pause', command=self._toggle_video_play, style='Small.TButton')
		self.video_play_btn.grid(row=0, column=0, padx=(0, 8))
		self.video_seek = ttk.Scale(self.video_controls, orient='horizontal', from_=0.0, to=1.0, variable=self._video_pos_var, command=self._on_video_seek)
		self.video_seek.grid(row=0, column=1, sticky='ew')
		self.video_time_lbl = ttk.Label(self.video_controls, text='00:00 / 00:00', style='Muted.TLabel')
		self.video_time_lbl.grid(row=0, column=2, padx=(8, 0))
		self.video_controls.grid_remove()
		# Audio controls (no autoplay). Simple play/pause button
		self.audio_controls = ttk.Frame(self.viewer_container, style='App.TFrame')
		self.audio_controls.grid(row=1, column=0, sticky='ew', padx=12, pady=(0, 10))
		self.audio_play_btn = ttk.Button(self.audio_controls, text='Play Audio', command=self._toggle_audio_play, style='Small.TButton')
		self.audio_play_btn.grid(row=0, column=0, padx=(0, 8))
		self.audio_controls.grid_remove()
		# Tagging input row (only visible in tagging mode)
		# Tag list row (visible in tagging mode)
		self.tagging_tags_frame = ttk.Frame(self.viewer_container, style='App.TFrame')
		self.tagging_tags_frame.grid(row=2, column=0, sticky='ew', padx=12, pady=(0, 6))
		self.tagging_tags_frame.grid_remove()
		# Tagging input row (only visible in tagging mode)
		self.tagging_input_frame = ttk.Frame(self.viewer_container, style='App.TFrame')
		self.tagging_input_frame.grid(row=3, column=0, sticky='ew', padx=12, pady=(0, 12))
		self.tagging_input_frame.columnconfigure(1, weight=1)
		lbl_tag = ttk.Label(self.tagging_input_frame, text='Add tag:', style='TLabel')
		lbl_tag.grid(row=0, column=0, padx=(0, 8))
		self.tagging_entry = ttk.Entry(self.tagging_input_frame, textvariable=self.tag_input_var)
		self.tagging_entry.grid(row=0, column=1, sticky='ew')
		self.tagging_entry.bind('<Return>', self._on_tagging_return)
		# Intercept navigation hotkeys while the entry has focus so they don't insert characters
		self.tagging_entry.bind('<Key>', self._on_tagging_entry_key)
		# Autocomplete bindings
		self.tagging_entry.bind('<KeyRelease>', self._on_tagging_entry_change)
		self.tagging_entry.bind('<Down>', self._on_tag_suggest_down)
		self.tagging_entry.bind('<Up>', self._on_tag_suggest_up)
		self.tagging_entry.bind('<Tab>', self._on_tag_suggest_accept)
		self.tagging_entry.bind('<Escape>', lambda e: (self._hide_tag_suggestions(), 'break'))
		self.tagging_entry.bind('<Left>', lambda e: self._on_tagging_entry_nav('left'))
		self.tagging_entry.bind('<Right>', lambda e: self._on_tagging_entry_nav('right'))
		self.tagging_input_frame.grid_remove()
		self.viewer_container.grid_remove()

		# Enable mouse-wheel scrolling globally so it works over all child widgets
		self._activate_mousewheel()

		# Apply app background
		self.root.configure(background=self.palette.get('root_bg', '#e9edf5'))
		# Ensure layout reflects initial non-view mode
		self._apply_view_mode_layout()

	def _setup_theme(self) -> None:
		style = ttk.Style()
		try:
			style.theme_use('clam')
		except Exception:
			pass
		# Palette
		if self.dark_mode:
			self.palette = {
				'bg': '#0f172a',
				'side_bg': '#111827',
				'text': '#f3f4f6',
				'muted': '#9ca3af',
				'primary': '#3b82f6',
				'primary_active': '#2563eb',
				'accent': '#34d399',
				'accent_active': '#10b981',
				'card_bg': '#1f2937',
				'card_hover_bg': '#273244',
				'selected_bg': '#1d4ed8',
				'tag_bg': '#1e293b',
				'tag_fg': '#93c5fd',
				'canvas_bg': '#0f172a',
				'root_bg': '#0b1220',
				'key_hint': '#fbbf24',
			}
		else:
			self.palette = {
				'bg': '#f6f7fb',
				'side_bg': '#ffffff',
				'text': '#111827',
				'muted': '#6b7280',
				'primary': '#2563eb',
				'primary_active': '#1d4ed8',
				'accent': '#10b981',
				'accent_active': '#059669',
				'card_bg': '#ffffff',
				'card_hover_bg': '#f3f4f6',
				'selected_bg': '#2563eb',
				'tag_bg': '#eef2ff',
				'tag_fg': '#3730a3',
				'canvas_bg': '#f6f7fb',
				'root_bg': '#e9edf5',
				'key_hint': '#b45309',
			}

		# Fonts
		base_font = tkfont.nametofont('TkDefaultFont')
		base_font.configure(family='Segoe UI', size=10)
		title_font = tkfont.nametofont('TkHeadingFont') if 'TkHeadingFont' in tkfont.names() else base_font.copy()
		title_font.configure(family='Segoe UI', size=14, weight='bold')

		# Base styles
		style.configure('App.TFrame', background=self.palette['bg'])
		style.configure('Side.TFrame', background=self.palette['side_bg'])
		style.configure('TLabel', background=self.palette['side_bg'], foreground=self.palette['text'])
		style.configure('Muted.TLabel', background=self.palette['side_bg'], foreground=self.palette['muted'])
		style.configure('Title.TLabel', background=self.palette['side_bg'], foreground=self.palette['text'], font=title_font)

		# Buttons
		style.configure('TButton', padding=(10, 6))
		style.configure('Primary.TButton', background=self.palette['primary'], foreground='#ffffff')
		style.map('Primary.TButton', background=[('active', self.palette['primary_active']), ('pressed', self.palette['primary_active'])])
		style.configure('Accent.TButton', background=self.palette['accent'], foreground='#ffffff')
		style.map('Accent.TButton', background=[('active', self.palette['accent_active']), ('pressed', self.palette['accent_active'])])
		style.configure('Small.TButton', padding=(6, 2))
		style.configure('HK.TCheckbutton', background=self.palette['side_bg'], foreground=self.palette['text'])
		style.configure('HKHint.TLabel', background=self.palette['side_bg'], foreground=self.palette['key_hint'])

		# Create rounded-corner button skins using 9-patch images
		self._install_rounded_button_theme(style)

		# Dark mode button overrides
		if self.dark_mode:
			style.configure('TButton', background='#374151', foreground='#ffffff')
			style.map('TButton', background=[('active', '#4b5563'), ('pressed', '#4b5563')])
			style.configure('Primary.TButton', background='#3b82f6', foreground='#ffffff')
			style.map('Primary.TButton', background=[('active', '#2563eb'), ('pressed', '#2563eb')])
			style.configure('Accent.TButton', background='#34d399', foreground='#ffffff')
			style.map('Accent.TButton', background=[('active', '#10b981'), ('pressed', '#10b981')])
			style.configure('Small.TButton', background='#374151', foreground='#ffffff')
			style.map('Small.TButton', background=[('active', '#4b5563'), ('pressed', '#4b5563')])
			style.configure('HK.TCheckbutton', background=self.palette['side_bg'], foreground=self.palette['text'])
			style.configure('HKHint.TLabel', background=self.palette['side_bg'], foreground=self.palette['key_hint'])

		# Cards and tags
		style.configure('Card.TFrame', background=self.palette['card_bg'])
		style.configure('Tag.TLabel', background=self.palette['tag_bg'], foreground=self.palette['tag_fg'], padding=(6, 2))

		# Fonts for hotkey list
		self._font_bold = tkfont.Font(family='Segoe UI', size=10, weight='bold')
		self._font_muted = tkfont.Font(family='Segoe UI', size=9)

		# Update container backgrounds if already created
		try:
			self.root.configure(background=self.palette['root_bg'])
			if hasattr(self, 'canvas') and isinstance(self.canvas, tk.Canvas):
				self.canvas.configure(background=self.palette['canvas_bg'])
		except Exception:
			pass

	def _install_rounded_button_theme(self, style: ttk.Style) -> None:
		# ttk does not support corner radius directly; use element create with images.
		# We'll synthesize simple rounded PNGs at runtime and register them.
		try:
			from PIL import ImageDraw
		except Exception:
			return
		def make_round_rect(w: int, h: int, r: int, color: tuple[int, int, int]) -> Image.Image:
			img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
			d = ImageDraw.Draw(img)
			d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=color)
			return img
		def tk_image_from_color(color_hex: str) -> tk.PhotoImage:
			c = color_hex.lstrip('#')
			r = int(c[0:2], 16); g = int(c[2:4], 16); b = int(c[4:6], 16)
			img = make_round_rect(20, 20, 6, (r, g, b, 255))
			return ImageTk.PhotoImage(img)
		# Base skins
		primary_img = tk_image_from_color(self.palette['primary'])
		primary_active_img = tk_image_from_color(self.palette['primary_active'])
		accent_img = tk_image_from_color(self.palette['accent'])
		accent_active_img = tk_image_from_color(self.palette['accent_active'])
		gray_img = tk_image_from_color('#374151' if self.dark_mode else '#e5e7eb')
		gray_active_img = tk_image_from_color('#4b5563' if self.dark_mode else '#d1d5db')
		# Register element using image (stretches well enough for flat buttons)
		style.element_create('RoundedButton', 'image', primary_img, ('active', primary_active_img), border=10, sticky='nswe')
		style.layout('Rounded.TButton', [('RoundedButton', {'sticky': 'nswe'}), ('Button.focus', {'children': [('Button.padding', {'children': [('Button.label', {'sticky': 'nswe'})], 'sticky': 'nswe'})], 'sticky': 'nswe'})])
		style.configure('Rounded.TButton', background='')
		# Map our existing button variants to rounded base
		style.layout('Primary.TButton', style.layout('Rounded.TButton'))
		style.layout('Accent.TButton', style.layout('Rounded.TButton'))
		style.layout('TButton', style.layout('Rounded.TButton'))
		style.element_create('RoundedGray', 'image', gray_img, ('active', gray_active_img), border=10, sticky='nswe')
		style.layout('Small.TButton', [('RoundedGray', {'sticky': 'nswe'}), ('Button.padding', {'children': [('Button.label', {'sticky': 'nswe'})], 'sticky': 'nswe'})])

	def _bind_mousewheel(self, widget: tk.Widget) -> None:
		widget.bind('<Enter>', lambda e: self._activate_mousewheel())
		widget.bind('<Leave>', lambda e: self._deactivate_mousewheel())

	def _activate_mousewheel(self) -> None:
		if sys.platform.startswith('linux'):
			self.root.bind_all('<Button-4>', self._on_mousewheel_linux)
			self.root.bind_all('<Button-5>', self._on_mousewheel_linux)
		else:
			self.root.bind_all('<MouseWheel>', self._on_mousewheel)

	def _deactivate_mousewheel(self) -> None:
		if sys.platform.startswith('linux'):
			self.root.unbind_all('<Button-4>')
			self.root.unbind_all('<Button-5>')
		else:
			self.root.unbind_all('<MouseWheel>')

	def _on_mousewheel(self, event: tk.Event) -> None:
		# Windows: event.delta in multiples of 120, macOS: typically small ints
		if sys.platform == 'darwin':
			step = -1 * int(event.delta)
		else:
			step = -1 * int(event.delta / 120)
		if step != 0:
			self.canvas.yview_scroll(step, 'units')

	def _on_mousewheel_linux(self, event: tk.Event) -> None:
		# X11 sends Button-4 (up) and Button-5 (down)
		if getattr(event, 'num', None) == 4:
			self.canvas.yview_scroll(-1, 'units')
		elif getattr(event, 'num', None) == 5:
			self.canvas.yview_scroll(1, 'units')

	def _on_canvas_configure(self, event: tk.Event) -> None:
		# Keep inner frame width equal to the canvas width
		try:
			# In normal mode, stretch inner frame to canvas width; in viewing mode, allow natural width for horizontal scrolling
			if not self.view_mode:
				self.canvas.itemconfigure(self.grid_window, width=event.width)
		except Exception:
			pass
		# Recompute desired number of columns based on available width, only if width meaningfully changed
		try:
			cw = int(event.width)
			if self._last_canvas_width is None or abs(cw - int(self._last_canvas_width)) >= 4:
				self._last_canvas_width = cw
				new_cols = self._compute_columns(max(1, cw))
				if new_cols != self._cols:
					self._cols = new_cols
					# If view mode, ensure frames cover all records; otherwise just reflow
					if self.view_mode:
						if len(self.card_frames) != len(self.records):
							self._render_grid()
						else:
							self._layout_cards()
					else:
						self._layout_cards()
		except Exception:
			pass
		# Adjust gallery target height based on window size in viewing mode (debounced)
		if self.view_mode and not self._freeze_gallery_height:
			try:
				new_h = max(100, int(self.root.winfo_height() * 0.28))
				if new_h != (self.gallery_height or 0):
					self.gallery_height = new_h
					# Debounce expensive re-render to avoid flicker
					if getattr(self, '_gallery_resize_after_id', None):
						try:
							self.root.after_cancel(self._gallery_resize_after_id)
						except Exception:
							pass
					self._gallery_resize_after_id = self.root.after(120, self._apply_gallery_resize)
			except Exception:
				pass
		# Update viewer render on resize in viewing mode
		if self.view_mode:
			# Avoid restarting active animations during resize to prevent flicker/crash; loops adapt sizing
			if not (self._is_video_playing() or self._is_gif_playing()):
				self._update_viewer_image()

	def _apply_gallery_resize(self) -> None:
		try:
			self._gallery_resize_after_id = None
			if not self.view_mode:
				return
			if isinstance(self.gallery_height, int):
				self.canvas.configure(height=int(self.gallery_height))
			# Thumbs need to be resized to match new height
			self._render_grid()
			self._scroll_selected_into_view()
		except Exception:
			pass

	def _compute_columns(self, available_width: int) -> int:
		# Approximate per-card width: thumbnail + frame padding + grid padding
		pad = 6 * 2  # left/right grid padding aggregate
		frame_pad = 8 * 2  # left/right internal padding
		card_w = int(self._thumb_px) + pad + frame_pad
		if self.view_mode and isinstance(self.force_cols, int) and self.force_cols > 0:
			return int(self.force_cols)
		return max(1, available_width // max(1, card_w))

	def _layout_cards(self) -> None:
		cols = max(1, self._cols)
		pad = 6
		for idx, frame in enumerate(self.card_frames):
			if self.view_mode:
				row = 0
				col = idx
			else:
				row = idx // cols
				col = idx % cols
			frame.grid_configure(row=row, column=col, padx=pad, pady=pad, sticky='n')
		self.grid_frame.update_idletasks()
		self.canvas.configure(scrollregion=self.canvas.bbox('all'))
		# If viewing mode active, set gallery height so thumbnails fit
		try:
			if self.view_mode:
				if not isinstance(self.gallery_height, int):
					self.gallery_height = max(100, int(self.root.winfo_height() * 0.28))
				self.canvas.configure(height=int(self.gallery_height))
			else:
				self.canvas.configure(height='')
		except Exception:
			pass

	def _bind_hotkeys(self) -> None:
		self.root.bind('<Key>', self.on_key)
		self.root.bind('<Control-KeyPress>', self.on_ctrl_key)
		self.root.bind('<Left>', self.on_arrow_left)
		self.root.bind('<Right>', self.on_arrow_right)

	def pick_folder(self) -> None:
		path = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.abspath('.'))
		if path:
			self.folder_var.set(path)
			set_last_root_dir(path)

	def scan_folder(self) -> None:
		root_dir = self.folder_var.get().strip()
		if not root_dir or not os.path.isdir(root_dir):
			messagebox.showerror('Scan', 'Please choose a valid folder')
			return
		files = list_media_files(root_dir)
		progress = tk.Toplevel(self.root)
		progress.title('Scanning...')
		lab = ttk.Label(progress, text='Scanning...')
		lab.pack(padx=20, pady=20)

		def on_progress(current: int, total: int, path: str) -> None:
			lab.configure(text=f'Scanning {current}/{total}')
			lab.update_idletasks()

		def run_scan() -> None:
			scan_directory(root_dir, self.db, on_progress=on_progress)
			progress.destroy()
			self.refresh_records()

		threading.Thread(target=run_scan, daemon=True).start()

	def refresh_records(self, preserve_selection: bool = False) -> None:
		root_dir = self.folder_var.get().strip() or None
		prev_selected: Set[int] = set()
		if preserve_selection:
			try:
				prev_selected = {int(x) for x in (self.selected_ids or set())}
			except Exception:
				prev_selected = set(self.selected_ids or set())
		# Build filters
		tags_text = (self.filter_tags_var.get() or '').strip()
		required_tags = [t.strip().lower() for t in tags_text.split(',') if t.strip()] or None
		match_all = bool(self.filter_match_all_var.get())
		try:
			records, total = self.db.query_media(required_tags=required_tags, search_text=None, limit=500, offset=0, root_dir=root_dir, tags_match_all=match_all)
		except TypeError:
			records, total = self.db.query_media(required_tags=required_tags, search_text=None, limit=500, offset=0)
			if root_dir:
				records = [r for r in records if os.path.abspath(r.root_dir) == os.path.abspath(root_dir)]
		self.records = records
		if preserve_selection:
			try:
				new_ids = {int(r.id) for r in self.records}
				self.selected_ids = {int(x) for x in prev_selected if int(x) in new_ids}
			except Exception:
				new_ids_fallback = set(getattr(r, 'id', None) for r in self.records)
				self.selected_ids = set(x for x in prev_selected if x in new_ids_fallback)
		else:
			self.selected_ids.clear()
		for w in self.grid_frame.winfo_children():
			w.destroy()
		self.photo_cache.clear()
		self._render_grid()
		# Initialize viewer in viewing/tagging mode
		if self.view_mode or self.tagging_mode:
			if self.current_view_id is None and self.records:
				self.current_view_id = self.records[0].id
			if self.view_mode:
				self._update_viewer_image()
			if self.tagging_mode:
				self._update_tagging_image()
				self._render_tagging_tags()

	def apply_filters(self) -> None:
		self.refresh_records()

	def _on_thumb_size_change(self, value: object) -> None:
		try:
			val = int(float(value))
		except Exception:
			return
		val = int(max(120, min(512, val)))
		# Update UI slider variable to not get stuck
		try:
			self.thumb_size_var.set(val)
		except Exception:
			pass
		self._thumb_px = val
		# Debounce heavy re-render so dragging feels smooth
		if getattr(self, '_thumb_apply_after_id', None):
			try:
				self.root.after_cancel(self._thumb_apply_after_id)
			except Exception:
				pass
		self._thumb_apply_after_id = self.root.after(250, self._apply_thumb_size_change)

	def _apply_thumb_size_change(self) -> None:
		set_thumb_size(self._thumb_px)
		self._cols = self._compute_columns(self.canvas.winfo_width() or int(self._thumb_px) * 2)
		self.refresh_records()
		self._thumb_apply_after_id = None

	def _render_grid(self) -> None:
		# Clear existing grid children to avoid layering old grid under viewing strip
		try:
			for w in self.grid_frame.winfo_children():
				w.destroy()
		except Exception:
			pass
		cols = max(1, self._cols)
		pad = 6
		self.card_frames = []
		for idx, rec in enumerate(self.records):
			if self.view_mode:
				row = 0
				col = idx
			else:
				row = idx // cols
				col = idx % cols
			frame = ttk.Frame(self.grid_frame, padding=8, style='Card.TFrame')
			frame.grid(row=row, column=col, padx=pad, pady=pad, sticky='n')
			frame.bind('<Button-1>', lambda e, rid=rec.id: self.on_item_click(e, rid))
			# Hover highlight
			def _on_enter(e, rid=rec.id, f=frame):
				style = ttk.Style()
				style_name = f'Card{rid}.TFrame'
				style.configure(style_name, background=self.palette.get('card_hover_bg', '#f3f4f6'))
				f.configure(style=style_name)
			def _on_leave(e, rid=rec.id, f=frame):
				self._update_card_style(f, rid)
			frame.bind('<Enter>', _on_enter)
			frame.bind('<Leave>', _on_leave)
			self.card_frames.append(frame)


			# Always prefer a square thumbnail sized to THUMB_SIZE with black bars
			thumb_path = None
			# Try from original file first (images); build_square_thumbnail is idempotent and cached by path
			if rec.file_path and os.path.exists(rec.file_path):
				thumb_path = build_square_thumbnail(rec.file_path)
			# If that failed (e.g., videos), try from an existing thumbnail image
			if not thumb_path and rec.thumbnail_path and os.path.exists(rec.thumbnail_path):
				thumb_path = build_square_thumbnail(rec.thumbnail_path)
			# Persist square path back to DB if we generated one and it's different
			try:
				if thumb_path and (rec.thumbnail_path != thumb_path) and str(rec.media_type).lower() != 'audio':
					self.db.update_thumbnail_path(rec.file_path or rec.thumbnail_path or '', thumb_path)
			except Exception:
				pass

			img_label = ttk.Label(frame)
			img_label.grid(row=1, column=0, padx=0, pady=0)
			img_label.bind('<Button-1>', lambda e, rid=rec.id: self.on_item_click(e, rid))
			# Fallbacks: show original image if available; audio uses placeholder
			if (not thumb_path) and str(rec.media_type).lower() == 'image' and rec.file_path and os.path.exists(rec.file_path):
				thumb_path = rec.file_path
			elif (not thumb_path) and str(rec.media_type).lower() == 'audio':
				thumb_path = build_audio_placeholder(size=int(self._thumb_px))
			if thumb_path and os.path.exists(thumb_path):
				try:
					pil_im = Image.open(thumb_path)
					# Resize to current thumb size with black bars if needed
					w, h = pil_im.size
					# Choose target square size: adapt to viewing mode strip height
					if self.view_mode and isinstance(self.gallery_height, int):
						size = max(60, int(self.gallery_height) - 40)
					else:
						size = int(self._thumb_px)
					scale = min(size / max(w, 1), size / max(h, 1))
					new_w = max(1, int(w * scale))
					new_h = max(1, int(h * scale))
					resized = pil_im.resize((new_w, new_h), Image.LANCZOS)
					canvas = Image.new('RGB', (size, size), color=(0, 0, 0))
					offset = ((size - new_w) // 2, (size - new_h) // 2)
					canvas.paste(resized, offset)
					photo = ImageTk.PhotoImage(canvas)
					self.photo_cache[rec.id] = photo
					img_label.configure(image=photo)
					# Keep a direct reference on the widget to avoid garbage collection
					img_label.image = photo
				except Exception:
					pass

			name_label = ttk.Label(frame, text=rec.file_name, width=40, wraplength=max(120, THUMB_SIZE), justify='center')
			name_label.grid(row=2, column=0, padx=0, pady=(4, 0))
			name_label.bind('<Button-1>', lambda e, rid=rec.id: self.on_item_click(e, rid))

			# Tags row
			tags = []
			try:
				tags = self.db.get_media_tags(rec.id)
			except Exception:
				pass
			if tags:
				row_tags = ttk.Frame(frame)
				row_tags.grid(row=3, column=0, pady=(2, 0))
				for t in tags:
					chip = ttk.Label(row_tags, text=f' {t} ', style='Tag.TLabel')
					chip.pack(side='left', padx=3, pady=1)

			self._update_card_style(frame, rec.id)

		# Ensure scrollregion covers all thumbnails after (re)render
		try:
			self.grid_frame.update_idletasks()
			self.canvas.configure(scrollregion=self.canvas.bbox('all'))
		except Exception:
			pass

	def _update_card_style(self, frame: ttk.Frame, media_id: int) -> None:
		selected = media_id in self.selected_ids
		style = ttk.Style()
		style_name = f'Card{media_id}.TFrame'
		if selected:
			bg = self.palette.get('selected_bg', '#1d4ed8')
			style.configure(style_name, background=bg, relief='solid', borderwidth=2)
		else:
			bg = self.palette.get('card_bg', '#ffffff')
			style.configure(style_name, background=bg, relief='flat', borderwidth=0)
		frame.configure(style=style_name)

	def toggle_view_mode(self) -> None:
		self.view_mode = not self.view_mode
		try:
			self.view_toggle_btn.configure(text=('Exit Viewing Mode' if self.view_mode else 'Enter Viewing Mode'))
		except Exception:
			pass
		self._apply_view_mode_layout()
		self._cols = self._compute_columns(self.canvas.winfo_width() or int(self._thumb_px) * 2)
		# Re-render grid to ensure all thumbnails exist in horizontal strip
		self._render_grid()
		if self.view_mode:
			# Keep current selection if available; otherwise select first
			if self.current_view_id is None:
				if self.selected_ids:
					# Choose an existing selected id if present in records
					try:
						sid = next((r.id for r in self.records if r.id in self.selected_ids), None)
						self.current_view_id = sid if sid is not None else (self.records[0].id if self.records else None)
					except Exception:
						self.current_view_id = self.records[0].id if self.records else None
				else:
					self.current_view_id = self.records[0].id if self.records else None
			self._update_viewer_image()
			self._scroll_selected_into_view()

	def _apply_view_mode_layout(self) -> None:
		self.force_cols = None
		try:
			if self.view_mode:
				self.viewer_container.grid()
				self.root.rowconfigure(1, weight=1)
				# Horizontal scrolling visible in viewing mode; hide vertical
				self.scroll_x.grid()
				self.scroll_y.grid_remove()
				# Let inner window use natural width so canvas can scroll horizontally
				try:
					self.canvas.itemconfigure(self.grid_window, width=0)
				except Exception:
					pass
				self.grid_frame.update_idletasks()
				# Set gallery strip height to a fraction of window so thumbnails fit
				self.gallery_height = max(100, int(self.root.winfo_height() * 0.28))
				self.canvas.configure(height=self.gallery_height)
				self._freeze_gallery_height = True
				self.canvas.configure(scrollregion=self.canvas.bbox('all'))
				self.canvas.xview_moveto(0)
			else:
				# Leaving viewing mode: stop any playback
				self._stop_media_playback()
				self.viewer_container.grid_remove()
				self.root.rowconfigure(1, weight=0)
				# Normal mode uses vertical scroll
				self.scroll_y.grid()
				self.scroll_x.grid_remove()
				# Stretch inner window to canvas width again
				try:
					self.canvas.itemconfigure(self.grid_window, width=self.canvas.winfo_width())
				except Exception:
					pass
				self._freeze_gallery_height = False
		except Exception:
			pass

	def toggle_tagging_mode(self) -> None:
		# Disable viewing mode if active
		if self.view_mode:
			self.view_mode = False
			try:
				self.view_toggle_btn.configure(text='Enter Viewing Mode')
			except Exception:
				pass
			self._apply_view_mode_layout()
		self.tagging_mode = not self.tagging_mode
		try:
			self.tagging_toggle_btn.configure(text=('Exit Tagging Mode' if self.tagging_mode else 'Enter Tagging Mode'))
		except Exception:
			pass
		self._apply_tagging_mode_layout()
		if self.tagging_mode:
			# Initialize current item if needed: prefer an image, then any with thumbnail, else first
			if self.current_view_id is None and self.records:
				chosen = None
				try:
					for r in self.records:
						if str(getattr(r, 'media_type', '')).lower() == 'image':
							chosen = r.id
							break
					if chosen is None:
						for r in self.records:
							if getattr(r, 'thumbnail_path', None):
								chosen = r.id
								break
					if chosen is None:
						chosen = self.records[0].id
				except Exception:
					chosen = self.records[0].id
				self.current_view_id = chosen
			# Ensure the selection matches the current
			if self.current_view_id is not None:
				try:
					self.selected_ids = {int(self.current_view_id)}
				except Exception:
					self.selected_ids = {self.current_view_id}
			self._update_tagging_image()
			self._render_tagging_tags()
			# Put keyboard focus into the tag input so typing works immediately
			try:
				self.tagging_entry.focus_set()
			except Exception:
				pass

	def _apply_tagging_mode_layout(self) -> None:
		try:
			if self.tagging_mode:
				# Hide grid canvas and scrollbars
				self.canvas.grid_remove()
				self.scroll_x.grid_remove()
				self.scroll_y.grid_remove()
				# Place viewer in bottom row and give it all space
				self.viewer_container.grid(row=1, column=1, sticky='nsew')
				self.root.rowconfigure(0, weight=0)
				self.root.rowconfigure(1, weight=1)
				# Ensure viewer row expands while controls/tag input stay visible
				try:
					self.viewer_container.rowconfigure(0, weight=1)
					self.viewer_container.rowconfigure(1, weight=0)
					self.viewer_container.rowconfigure(2, weight=0)
					self.viewer_container.rowconfigure(3, weight=0)
				except Exception:
					pass
				# Show tagging input
				self.tagging_tags_frame.grid()
				self.tagging_input_frame.grid()
				# Show tagging nav config in sidebar
				self.tagging_nav_frame.pack(fill='x', pady=(6, 0))
				# Controls will be shown/hidden per media in _update_tagging_image
			else:
				# Ensure autocomplete popup is removed when leaving tagging mode
				self._hide_tag_suggestions()
				# Restore grid canvas
				self.canvas.grid(row=0, column=0, sticky='nsew')
				self.scroll_y.grid(row=0, column=1, sticky='ns')
				# Horizontal scroll hidden by default
				self.scroll_x.grid_remove()
				# Hide viewer unless viewing mode will show it
				if not self.view_mode:
					self.viewer_container.grid_remove()
				# Hide tagging UI
				self.tagging_tags_frame.grid_remove()
				self.tagging_input_frame.grid_remove()
				self.tagging_nav_frame.pack_forget()
				# Reset row weights and canvas height for normal gallery mode
				try:
					self.root.rowconfigure(0, weight=1)
					self.root.rowconfigure(1, weight=0)
					self.canvas.itemconfigure(self.grid_window, width=self.canvas.winfo_width())
					self.canvas.configure(height='')
				except Exception:
					pass
		except Exception:
			pass

	def _update_tagging_image(self) -> None:
		if not self.tagging_mode:
			return
		# Render current record similarly to viewing mode but scaled to occupy most of the window
		rec = self._find_record_by_id(self.current_view_id)
		if not rec:
			try:
				self.viewer_label.configure(image='')
				self.viewer_label.image = None  # type: ignore[attr-defined]
			except Exception:
				pass
			return
		# Determine media type and stop previous playback if changed
		mt = str(getattr(rec, 'media_type', '')).lower()
		try:
			cur_id = int(getattr(rec, 'id', -1))
		except Exception:
			cur_id = getattr(rec, 'id', -1)
		changed = (self._viewer_current_id != cur_id) or (self._viewer_current_type != mt)
		if changed:
			self._stop_media_playback()
			self._viewer_current_id = cur_id
			self._viewer_current_type = mt
		# Hide controls by default
		try:
			self.video_controls.grid_remove()
			self.audio_controls.grid_remove()
		except Exception:
			pass
		# Compute available area inside viewer container
		try:
			self.viewer_container.update_idletasks()
			vc_w = int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 1280)
			vc_h = int(self.viewer_container.winfo_height() or 600)
			avail_w = max(200, vc_w - 16)
			try:
				reserved_tags = int(self.tagging_tags_frame.winfo_height() or self.tagging_tags_frame.winfo_reqheight() or 0)
			except Exception:
				reserved_tags = 0
			try:
				reserved_input = int(self.tagging_input_frame.winfo_height() or self.tagging_input_frame.winfo_reqheight() or 0)
			except Exception:
				reserved_input = 80
			reserved_h = reserved_tags + reserved_input + 24
			avail_h = max(200, vc_h - reserved_h)
		except Exception:
			avail_w, avail_h = 1000, 700
		# Branch by media type
		if mt == 'image' and rec.file_path and os.path.exists(rec.file_path):
			try:
				with Image.open(rec.file_path) as im:
					im = im.convert('RGB')
					w, h = im.size
					scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
					new_w = max(1, int(w * scale))
					new_h = max(1, int(h * scale))
					resized = im.resize((new_w, new_h), Image.LANCZOS)
					canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
					offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
					canvas_img.paste(resized, offset)
					photo = ImageTk.PhotoImage(canvas_img)
					self._set_viewer_photo(photo)
					self._render_tagging_tags()
					return
			except Exception:
				pass
		if mt == 'video' and rec.file_path and os.path.exists(rec.file_path):
			# Show controls, no autoplay. Probe metadata and render first frame if possible
			try:
				self.video_controls.grid()
				self._video_pause = True
				self.video_play_btn.configure(text='Play')
				try:
					import cv2  # type: ignore
					cap_probe = cv2.VideoCapture(rec.file_path)
					if cap_probe.isOpened():
						fps = float(cap_probe.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
						total_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
						duration = (total_frames / fps) if fps > 0 else 0.0
						cap_probe.release()
					else:
						fps = 30.0; duration = 0.0
					self._video_fps = fps
					self._video_duration_s = duration
					self._video_updating_slider = True
					self.video_seek.configure(from_=0.0, to=max(0.01, float(duration) or 0.01))
					self._video_pos_var.set(0.0)
					self._video_updating_slider = False
					self.video_time_lbl.configure(text=f"00:00 / {self._format_time(duration)}")
				except Exception:
					pass
				try:
					import cv2  # type: ignore
					cap = cv2.VideoCapture(rec.file_path)
					ok, frame = cap.read()
					if ok:
						frame_rgb = frame[:, :, ::-1]
						img = Image.fromarray(frame_rgb)
						w, h = img.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = img.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self._set_viewer_photo(photo)
					cap.release()
				except Exception:
					pass
				self._render_tagging_tags()
				return
			except Exception:
				pass
		if mt == 'audio':
			try:
				self.audio_controls.grid()
				self.audio_play_btn.configure(text='Play Audio')
				self.video_controls.grid_remove()
			except Exception:
				pass
			path = build_audio_placeholder(size=max(480, int(self._thumb_px) * 2))
			if path and os.path.exists(path):
				try:
					with Image.open(path) as im:
						im = im.convert('RGB')
						w, h = im.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = im.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self._set_viewer_photo(photo)
						self._render_tagging_tags()
						return
				except Exception:
					pass
		# Video fallback to thumbnail/placeholder
		if mt == 'video':
			path = getattr(rec, 'thumbnail_path', None)
			if path and os.path.exists(path):
				try:
					with Image.open(path) as im:
						im = im.convert('RGB')
						w, h = im.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = im.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self._set_viewer_photo(photo)
						self._render_tagging_tags()
						return
				except Exception:
					pass
			# No thumbnail available: use audio-style placeholder as a badge
			ph = build_audio_placeholder(size=max(480, int(self._thumb_px) * 2))
			if ph and os.path.exists(ph):
				try:
					with Image.open(ph) as im:
						im = im.convert('RGB')
						w, h = im.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = im.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self._set_viewer_photo(photo)
						return
				except Exception:
					pass
		# Generic fallback to thumbnail
		path = rec.thumbnail_path if getattr(rec, 'thumbnail_path', None) else None
		if path and os.path.exists(path):
			try:
				with Image.open(path) as im:
					im = im.convert('RGB')
					w, h = im.size
					scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
					new_w = max(1, int(w * scale))
					new_h = max(1, int(h * scale))
					resized = im.resize((new_w, new_h), Image.LANCZOS)
					canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
					offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
					canvas_img.paste(resized, offset)
					photo = ImageTk.PhotoImage(canvas_img)
					self._set_viewer_photo(photo)
					self._render_tagging_tags()
					return
			except Exception:
				pass

	def _on_tagging_enter(self, event: tk.Event) -> None:
		# Accept and hide suggestions if visible
		self._hide_tag_suggestions()
		text = (self.tag_input_var.get() or '').strip().lower()
		if not text:
			return
		if self.current_view_id is None:
			self.tag_input_var.set('')
			return
		try:
			self.db.add_media_tags(int(self.current_view_id), [text])
		except Exception:
			try:
				self.db.add_media_tags(self.current_view_id, [text])
			except Exception:
				pass
		self.tag_input_var.set('')
		self.refresh_records(preserve_selection=True)
		self._show_toast(f"Added '{text}'")
		# Update visible tag list and keep focus for rapid entry
		try:
			self._render_tagging_tags()
			self.tagging_entry.focus_set()
		except Exception:
			pass

	def _apply_tagging_keys(self) -> None:
		prev_k = (self.tag_prev_key_var.get() or '').strip().lower() or 'a'
		next_k = (self.tag_next_key_var.get() or '').strip().lower() or 'd'
		self.tag_prev_key = prev_k
		self.tag_next_key = next_k
		set_tagging_nav_keys(prev_k, next_k)
		# Reflect in UI label for last key and keep focus in entry
		try:
			self.last_key_var.set(f'Tagging keys: {self.tag_prev_key}/{self.tag_next_key}')
			self.tagging_entry.focus_set()
		except Exception:
			pass

	def _find_record_by_id(self, mid: Optional[int]) -> Optional[MediaRecord]:
		if mid is None:
			return None
		for r in self.records:
			if int(r.id) == int(mid):
				return r
		return None

	def _update_viewer_image(self) -> None:
		if not self.view_mode:
			return
		# Increment session to invalidate stale async updates from previous media
		try:
			self._viewer_session += 1
		except Exception:
			self._viewer_session = int(self._viewer_session) + 1 if isinstance(self._viewer_session, int) else 1
		current_session = int(self._viewer_session)
		rec = self._find_record_by_id(self.current_view_id)
		if not rec:
			try:
				self.viewer_label.configure(image='')
				self.viewer_label.image = None  # type: ignore[attr-defined]
			except Exception:
				pass
			# Clear viewer state when nothing is selected
			self._viewer_current_id = None
			self._viewer_current_type = None
			return
		# Determine media type and whether it changed since last render
		mt = str(getattr(rec, 'media_type', '')).lower()
		cur_id = int(getattr(rec, 'id', -1))
		changed = (self._viewer_current_id != cur_id) or (self._viewer_current_type != mt)
		# Only stop/reconfigure playback when the selected media actually changes
		if changed:
			self._stop_media_playback()
			self._viewer_current_id = cur_id
			self._viewer_current_type = mt
		# Compute available render area for viewer
		try:
			self.viewer_container.update_idletasks()
			avail_w = max(200, int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 800) - 16)
			avail_h = max(200, int(self.root.winfo_height() * 0.55))
		except Exception:
			avail_w, avail_h = 800, 500
		# Images: render full resolution scaled, not thumbnails
		if mt == 'image' and rec.file_path and os.path.exists(rec.file_path):
			# Animated GIF support: play animation instead of static render
			try:
				_, ext = os.path.splitext(rec.file_path)
				if ext.lower() == '.gif':
					self._start_gif_playback(rec.file_path, current_session)
					return
			except Exception:
				pass
			try:
				with Image.open(rec.file_path) as im:
					im = im.convert('RGB')
					w, h = im.size
					scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
					new_w = max(1, int(w * scale))
					new_h = max(1, int(h * scale))
					resized = im.resize((new_w, new_h), Image.LANCZOS)
					canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
					offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
					canvas_img.paste(resized, offset)
					photo = ImageTk.PhotoImage(canvas_img)
					self.viewer_photo = photo
					self.viewer_label.configure(image=photo)
					self.viewer_label.image = photo  # type: ignore[attr-defined]
			except Exception:
				pass
			return
		# Video: play the actual video in the bottom viewer if possible
		if mt == 'video' and rec.file_path and os.path.exists(rec.file_path):
			self._start_video_playback(rec.file_path, current_session)
			return
		# Audio: do not autoplay; show placeholder and audio controls
		if mt == 'audio' and rec.file_path and os.path.exists(rec.file_path):
			# Show audio controls (only adjust visibility when media changed)
			if changed:
				try:
					self.audio_controls.grid()
					self.audio_play_btn.configure(text='Play Audio')
					# Ensure video controls are hidden for audio files
					self.video_controls.grid_remove()
				except Exception:
					pass
			# Render placeholder image sized to viewer (safe to do on resize without restarting anything)
			path = build_audio_placeholder(size=max(480, int(self._thumb_px) * 2))
			if path and os.path.exists(path):
				try:
					with Image.open(path) as im:
						im = im.convert('RGB')
						w, h = im.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = im.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self.viewer_photo = photo
						self.viewer_label.configure(image=photo)
						self.viewer_label.image = photo  # type: ignore[attr-defined]
				except Exception:
					pass
			return
		# Fallback: show any available thumbnail
		path = rec.thumbnail_path if getattr(rec, 'thumbnail_path', None) else None
		if not path or not os.path.exists(path):
			return
		try:
			with Image.open(path) as im:
				im = im.convert('RGB')
				w, h = im.size
				scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
				new_w = max(1, int(w * scale))
				new_h = max(1, int(h * scale))
				resized = im.resize((new_w, new_h), Image.LANCZOS)
				canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
				offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
				canvas_img.paste(resized, offset)
				photo = ImageTk.PhotoImage(canvas_img)
				self.viewer_photo = photo
				self.viewer_label.configure(image=photo)
				self.viewer_label.image = photo  # type: ignore[attr-defined]
		except Exception:
			pass

	def _stop_media_playback(self) -> None:
		# Stop video thread if running
		try:
			if self._video_stop_event is not None:
				self._video_stop_event.set()
			if self._video_thread is not None and self._video_thread.is_alive():
				self._video_thread.join(timeout=0.5)
		finally:
			self._video_thread = None
			self._video_stop_event = None
			self._video_path_playing = None
			self._video_pause = False
			self._video_total_frames = 0
			self._video_fps = 0.0
			self._video_duration_s = 0.0
			self._video_current_frame = 0
			self._video_seek_to_frame = None
			# Hide controls
			try:
				self.video_controls.grid_remove()
			except Exception:
				pass
			try:
				self.audio_controls.grid_remove()
			except Exception:
				pass
		# Stop GIF thread if running
		try:
			if self._gif_stop_event is not None:
				self._gif_stop_event.set()
			if self._gif_thread is not None and self._gif_thread.is_alive():
				self._gif_thread.join(timeout=0.5)
		finally:
			self._gif_thread = None
			self._gif_stop_event = None
			self._gif_path_playing = None
			self._gif_pause = False
		# Stop audio subprocess if running
		self._terminate_audio_proc()

	def _terminate_audio_proc(self) -> None:
		try:
			if self._audio_proc is not None:
				try:
					self._audio_proc.terminate()
					# Give it a moment to exit, then force kill if still alive
					for _ in range(10):
						if self._audio_proc.poll() is not None:
							break
						time.sleep(0.02)
					if self._audio_proc.poll() is None:
						self._audio_proc.kill()
				except Exception:
					pass
				finally:
					self._audio_proc = None
		except Exception:
			self._audio_proc = None

	def _on_close(self) -> None:
		# Ensure background playback is fully stopped when window closes
		try:
			self._stop_media_playback()
		except Exception:
			pass
		try:
			self.root.destroy()
		except Exception:
			pass

	def _is_video_playing(self) -> bool:
		try:
			return bool(self._video_thread and self._video_thread.is_alive() and self._video_path_playing)
		except Exception:
			return False

	def _is_gif_playing(self) -> bool:
		try:
			return bool(self._gif_thread and self._gif_thread.is_alive() and self._gif_path_playing)
		except Exception:
			return False

	def _start_gif_playback(self, path: str, session: int) -> None:
		# Play animated GIF frames in a loop using PIL
		try:
			with Image.open(path) as test_im:
				is_anim = bool(getattr(test_im, 'is_animated', False))
				n_frames = int(getattr(test_im, 'n_frames', 1) or 1)
				if (not is_anim) or n_frames <= 1:
					# Not animated: render static
					try:
						self.viewer_container.update_idletasks()
						avail_w = max(200, int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 800) - 16)
						avail_h = max(200, int(self.root.winfo_height() * 0.55))
						with Image.open(path) as im:
							im = im.convert('RGB')
							w, h = im.size
							scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
							new_w = max(1, int(w * scale))
							new_h = max(1, int(h * scale))
							resized = im.resize((new_w, new_h), Image.LANCZOS)
							canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
							offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
							canvas_img.paste(resized, offset)
							photo = ImageTk.PhotoImage(canvas_img)
							self.viewer_photo = photo
							self.viewer_label.configure(image=photo)
							self.viewer_label.image = photo  # type: ignore[attr-defined]
					except Exception:
						pass
					return
		except Exception:
			return
		# If we reach here, we have an animated GIF; start thread
		self._gif_stop_event = threading.Event()
		stop_event = self._gif_stop_event
		self._gif_path_playing = path
		self._gif_pause = False
		# Clear stale image
		try:
			self.viewer_label.configure(image='')
			self.viewer_label.image = None  # type: ignore[attr-defined]
		except Exception:
			pass
		def run() -> None:
			try:
				im = Image.open(path)
				while not stop_event.is_set():
					for frame_index in range(int(getattr(im, 'n_frames', 1) or 1)):
						if stop_event.is_set():
							break
						try:
							im.seek(frame_index)
							frame = im.convert('RGBA')
							# Determine available space dynamically
							try:
								self.viewer_container.update_idletasks()
								avail_w = max(200, int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 800) - 16)
								avail_h = max(200, int(self.root.winfo_height() * 0.55))
							except Exception:
								avail_w, avail_h = 800, 500
							w, h = frame.size
							scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
							new_w = max(1, int(w * scale))
							new_h = max(1, int(h * scale))
							resized = frame.resize((new_w, new_h), Image.LANCZOS)
							canvas_img = Image.new('RGBA', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0, 255))
							offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
							canvas_img.paste(resized, offset, resized)
							photo = ImageTk.PhotoImage(canvas_img)
							self.root.after(0, self._set_viewer_photo_if_current, photo, session)
							# Frame delay
							delay_ms = int(im.info.get('duration', 100) or 100)
							# Pause loop
							end_time = time.time() + max(0.001, delay_ms / 1000.0)
							while time.time() < end_time:
								if stop_event.is_set():
									break
								if self._gif_pause:
									time.sleep(0.02)
									continue
								time.sleep(0.005)
						except Exception:
							break
				im.close()
			except Exception:
				pass
		self._gif_thread = threading.Thread(target=run, daemon=True)
		self._gif_thread.start()
	def _start_video_playback(self, path: str, session: int) -> None:
		# Attempt to play video frames in the label using OpenCV if available
		try:
			import cv2  # type: ignore
		except Exception:
			# Fallback to showing thumbnail if cv2 not available
			thumb = getattr(self._find_record_by_id(self.current_view_id), 'thumbnail_path', None)
			if thumb and os.path.exists(thumb):
				try:
					with Image.open(thumb) as im:
						im = im.convert('RGB')
						# Determine available space dynamically
						self.viewer_container.update_idletasks()
						avail_w = max(200, int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 800) - 16)
						avail_h = max(200, int(self.root.winfo_height() * 0.55))
						w, h = im.size
						scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
						new_w = max(1, int(w * scale))
						new_h = max(1, int(h * scale))
						resized = im.resize((new_w, new_h), Image.LANCZOS)
						canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
						offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
						canvas_img.paste(resized, offset)
						photo = ImageTk.PhotoImage(canvas_img)
						self.viewer_photo = photo
						self.viewer_label.configure(image=photo)
						self.viewer_label.image = photo  # type: ignore[attr-defined]
				except Exception:
					pass
			return
		self._video_stop_event = threading.Event()
		stop_event = self._video_stop_event
		self._video_path_playing = path
		# Clear any image so we don't show stale frames
		# Do not clear image immediately to avoid flicker before first frame
		# Initialize capture metadata and show controls
		try:
			cap_probe = cv2.VideoCapture(path)
			if cap_probe.isOpened():
				self._video_fps = float(cap_probe.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
				self._video_total_frames = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
				self._video_duration_s = (self._video_total_frames / self._video_fps) if self._video_fps > 0 else 0.0
				cap_probe.release()
			else:
				self._video_fps = 30.0
				self._video_total_frames = 0
				self._video_duration_s = 0.0
		except Exception:
			self._video_fps = 30.0
			self._video_total_frames = 0
			self._video_duration_s = 0.0
		# Configure controls
		try:
			self.video_controls.grid()
			self._video_pause = False
			self.video_play_btn.configure(text='Pause')
			self._video_updating_slider = True
			self.video_seek.configure(from_=0.0, to=max(0.01, float(self._video_duration_s) or 0.01))
			self._video_pos_var.set(0.0)
			self._video_updating_slider = False
			self.video_time_lbl.configure(text=f"00:00 / {self._format_time(self._video_duration_s)}")
			# Initialize clock for A/V sync
			self._video_clock_offset = 0.0
			self._video_clock_start = time.monotonic()
			# Hide audio controls while video is active
			try:
				self.audio_controls.grid_remove()
			except Exception:
				pass
		except Exception:
			pass
		def run() -> None:
			try:
				cap = cv2.VideoCapture(path)
				if not cap.isOpened():
					return
				fps = float(cap.get(cv2.CAP_PROP_FPS) or self._video_fps or 30.0)
				if not fps or fps <= 0:
					fps = 30.0
				interval = 1.0 / float(max(1.0, fps))
				# Ensure audio starts at t=0 when playback begins (only if still current)
				try:
					self.root.after(0, self._restart_video_audio, 0.0, session)
				except Exception:
					pass
				while not stop_event.is_set():
					# Apply pending seek
					if self._video_seek_to_frame is not None:
						with self._video_lock:
							seek_frame = int(self._video_seek_to_frame)
							self._video_seek_to_frame = None
						cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, seek_frame))
						self._video_current_frame = max(0, seek_frame)
					# Handle pause
					if self._video_pause:
						time.sleep(0.05)
						continue
					# Real-time sync: compute target frame from clock
					try:
						elapsed = float(time.monotonic() - self._video_clock_start)
						media_pos = float(self._video_clock_offset + max(0.0, elapsed))
						desired_frame = int(media_pos * fps)
						cur_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or self._video_current_frame)
						if desired_frame > cur_frame + 1:
							cap.set(cv2.CAP_PROP_POS_FRAMES, desired_frame)
							self._video_current_frame = desired_frame
					except Exception:
						pass
					ok, frame = cap.read()
					if not ok:
						break
					# Convert BGR to RGB
					frame_rgb = frame[:, :, ::-1]
					img = Image.fromarray(frame_rgb)
					# Determine available space dynamically and letterbox
					try:
						self.viewer_container.update_idletasks()
						avail_w = max(200, int(self.viewer_container.winfo_width() or self.canvas.winfo_width() or 800) - 16)
						avail_h = max(200, int(self.root.winfo_height() * 0.55))
					except Exception:
						avail_w, avail_h = 800, 500
					w, h = img.size
					scale = min(avail_w / max(w, 1), avail_h / max(h, 1))
					new_w = max(1, int(w * scale))
					new_h = max(1, int(h * scale))
					resized = img.resize((new_w, new_h), Image.LANCZOS)
					canvas_img = Image.new('RGB', (max(avail_w, new_w), max(avail_h, new_h)), color=(0, 0, 0))
					offset = ((canvas_img.width - new_w) // 2, (canvas_img.height - new_h) // 2)
					canvas_img.paste(resized, offset)
					photo = ImageTk.PhotoImage(canvas_img)
					# Schedule UI update in main thread, guarded by session
					self.root.after(0, self._set_viewer_photo_if_current, photo, session)
					# Update time/seek UI
					try:
						pos_frames = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or self._video_current_frame or 0)
						self._video_current_frame = pos_frames
						pos_sec = float(pos_frames) / float(fps)
						self.root.after(0, self._update_video_seek_ui_if_current, pos_sec, session)
					except Exception:
						pass
					# Sleep until the next frame time to throttle
					try:
						elapsed = float(time.monotonic() - self._video_clock_start)
						media_pos = float(self._video_clock_offset + max(0.0, elapsed))
						next_frame_time = float((self._video_current_frame + 1) / fps)
						delay = max(0.0, next_frame_time - media_pos)
						if delay > 0.02:
							delay = 0.02
						time.sleep(delay)
					except Exception:
						time.sleep(interval)
				cap.release()
			except Exception:
				pass
		self._video_thread = threading.Thread(target=run, daemon=True)
		self._video_thread.start()

	def _restart_video_audio(self, pos_sec: float, session: Optional[int] = None) -> None:
		# Start or restart ffplay at the given position to play video audio
		try:
			# Ignore if this callback is stale
			if session is not None and int(session) != int(self._viewer_session):
				return
			if not self._video_path_playing:
				return
			# Kill any existing audio proc first
			self._terminate_audio_proc()
			if shutil.which('ffplay'):
				# Use -ss to start near the requested time
				cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'error', '-ss', f"{max(0.0, float(pos_sec)):.3f}", self._video_path_playing]
				startupinfo = None
				creationflags = 0
				if sys.platform.startswith('win'):
					try:
						startupinfo = subprocess.STARTUPINFO()
						startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
						creationflags = (getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
					except Exception:
						startupinfo = None
						creationflags = 0
				self._audio_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, creationflags=creationflags)
		except Exception:
			self._audio_proc = None

	def _update_video_seek_ui(self, pos_sec: float) -> None:
		try:
			self._video_updating_slider = True
			self._video_pos_var.set(max(0.0, float(pos_sec)))
			self._video_updating_slider = False
			total = self._video_duration_s
			self.video_time_lbl.configure(text=f"{self._format_time(pos_sec)} / {self._format_time(total)}")
		except Exception:
			pass

	def _update_video_seek_ui_if_current(self, pos_sec: float, session: int) -> None:
		try:
			if int(session) != int(self._viewer_session):
				return
			self._video_updating_slider = True
			self._video_pos_var.set(max(0.0, float(pos_sec)))
			self._video_updating_slider = False
			total = self._video_duration_s
			self.video_time_lbl.configure(text=f"{self._format_time(pos_sec)} / {self._format_time(total)}")
		except Exception:
			pass

	def _toggle_video_play(self) -> None:
		try:
			# If no video is currently playing, start playback for the selected video
			if not self._is_video_playing():
				rec = self._find_record_by_id(self.current_view_id)
				if rec and str(getattr(rec, 'media_type', '')).lower() == 'video' and rec.file_path and os.path.exists(rec.file_path):
					# Increment session to keep A/V sync semantics consistent
					try:
						self._viewer_session += 1
					except Exception:
						self._viewer_session = int(self._viewer_session) + 1 if isinstance(self._viewer_session, int) else 1
					self._start_video_playback(rec.file_path, int(self._viewer_session))
					return
			self._video_pause = not self._video_pause
			self.video_play_btn.configure(text=('Play' if self._video_pause else 'Pause'))
			# Sync audio with pause/resume
			if self._video_pause:
				# Stop audio
				try:
					if self._audio_proc is not None:
						self._audio_proc.terminate()
						self._audio_proc = None
				except Exception:
					self._audio_proc = None
			else:
				# Resume audio near current position
				fps = float(self._video_fps or 30.0)
				pos_sec = float(max(0, int(self._video_current_frame)))/fps
				# Reset clock so real-time sync resumes from current pos
				self._video_clock_offset = float(pos_sec)
				self._video_clock_start = time.monotonic()
				self._restart_video_audio(pos_sec, int(self._viewer_session))
		except Exception:
			pass

	def _on_video_seek(self, value: object) -> None:
		# Ignore callback if we are updating slider programmatically
		if self._video_updating_slider:
			return
		try:
			sec = float(value) if value is not None else 0.0
			fps = float(self._video_fps or 30.0)
			frame = int(max(0, sec * fps))
			with self._video_lock:
				self._video_seek_to_frame = frame
			# If playing, restart audio at new position
			if not self._video_pause:
				self._restart_video_audio(sec, int(self._viewer_session))
			# Reset clock to the new seek position
			self._video_clock_offset = float(sec)
			self._video_clock_start = time.monotonic()
		except Exception:
			pass

	def _format_time(self, seconds: float) -> str:
		try:
			s = int(max(0, seconds))
			m, s = divmod(s, 60)
			h, m = divmod(m, 60)
			if h > 0:
				return f"{h:02d}:{m:02d}:{s:02d}"
			return f"{m:02d}:{s:02d}"
		except Exception:
			return "00:00"

	def _set_viewer_photo(self, photo: ImageTk.PhotoImage) -> None:
		try:
			self.viewer_photo = photo
			self.viewer_label.configure(image=photo)
			self.viewer_label.image = photo  # type: ignore[attr-defined]
		except Exception:
			pass

	def _set_viewer_photo_if_current(self, photo: ImageTk.PhotoImage, session: int) -> None:
		try:
			if int(session) != int(self._viewer_session):
				return
			self.viewer_photo = photo
			self.viewer_label.configure(image=photo)
			self.viewer_label.image = photo  # type: ignore[attr-defined]
		except Exception:
			pass

	def _start_audio_playback(self, path: str) -> None:
		# Prefer ffplay if available for broad codec support
		try:
			if shutil.which('ffplay'):
				startupinfo = None
				creationflags = 0
				if sys.platform.startswith('win'):
					try:
						startupinfo = subprocess.STARTUPINFO()
						startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
						creationflags = (getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
					except Exception:
						startupinfo = None
						creationflags = 0
				self._audio_proc = subprocess.Popen(['ffplay', '-nodisp', '-autoexit', '-loglevel', 'error', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, creationflags=creationflags)
				return
		except Exception:
			self._audio_proc = None
		# Try playsound as a very simple fallback if installed
		try:
			from playsound import playsound  # type: ignore
		except Exception:
			playsound = None  # type: ignore
		if playsound is not None:
			def _run() -> None:
				try:
					playsound(path)
				except Exception:
					pass
			threading.Thread(target=_run, daemon=True).start()

	def _toggle_audio_play(self) -> None:
		try:
			# If an audio process is running, stop it
			if self._audio_proc is not None and (self._audio_proc.poll() is None):
				self._terminate_audio_proc()
				try:
					self.audio_play_btn.configure(text='Play Audio')
				except Exception:
					pass
				return
			# Otherwise, start playback for the currently selected audio file
			rec = self._find_record_by_id(self.current_view_id)
			if rec and str(getattr(rec, 'media_type', '')).lower() == 'audio' and rec.file_path and os.path.exists(rec.file_path):
				self._start_audio_playback(rec.file_path)
				try:
					self.audio_play_btn.configure(text='Pause Audio')
				except Exception:
					pass
		except Exception:
			pass

	def open_settings(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title('Settings')
		dialog.transient(self.root)
		dialog.grab_set()
		frm = ttk.Frame(dialog, padding=12)
		frm.pack(fill='both', expand=True)
		dark_var = tk.BooleanVar(value=bool(self.dark_mode))
		chk = ttk.Checkbutton(frm, text='Enable dark mode', variable=dark_var, command=lambda: self._toggle_dark_mode(dark_var.get()))
		chk.pack(anchor='w', pady=(0, 8))
		lbl = ttk.Label(frm, text='Manage hotkeys in the left panel.', style='Muted.TLabel')
		lbl.pack(anchor='w')

	def _toggle_dark_mode(self, enabled: bool) -> None:
		self.dark_mode = bool(enabled)
		set_dark_mode(self.dark_mode)
		# Close any transient autocomplete so it will pick up new theme on next open
		self._hide_tag_suggestions()
		self._setup_theme()
		# Refresh card styles and canvas bg
		try:
			self.canvas.configure(background=self.palette.get('canvas_bg', '#f6f7fb'))
		except Exception:
			pass
		self._refresh_card_styles()
		# Re-render hotkey list to reflect theme
		try:
			self._render_hotkey_list()
		except Exception:
			pass
		# Ensure proper layout after render (in case canvas width changed recently)
		self._layout_cards()

	def _render_hotkey_list(self) -> None:
		if not hasattr(self, 'hotkey_list_frame'):
			return
		for w in self.hotkey_list_frame.winfo_children():
			w.destroy()
		if not self.hotkeys:
			lbl = ttk.Label(self.hotkey_list_frame, text='No hotkeys yet', style='Muted.TLabel')
			lbl.pack(anchor='w')
			return
		for k in sorted(self.hotkeys.keys()):
			row = ttk.Frame(self.hotkey_list_frame, style='Side.TFrame')
			row.pack(fill='x', pady=2)
			var = tk.BooleanVar(value=False)
			chk = ttk.Checkbutton(row, variable=var, style='HK.TCheckbutton', command=lambda key=k, v=var: self._toggle_sidebar_tag(key, v.get()))
			chk.pack(side='left')
			# Tag name bolded
			tag_text = self.hotkeys.get(k, '')
			tag_lbl = ttk.Label(row, text=tag_text)
			tag_lbl.configure(font=self._font_bold)
			tag_lbl.pack(side='left', padx=(6, 6))
			# Key hint
			key_lbl = ttk.Label(row, text=f"({k})", style='HKHint.TLabel')
			key_lbl.pack(side='left')
			btn = ttk.Button(row, text='Remove', style='Small.TButton', command=lambda key=k: self._remove_hotkey_mapping(key))
			btn.pack(side='right')

	def _render_tagging_tags(self) -> None:
		# Render chips for current item's tags in tagging mode
		if not hasattr(self, 'tagging_tags_frame'):
			return
		for w in self.tagging_tags_frame.winfo_children():
			w.destroy()
		if not self.tagging_mode:
			return
		rec = self._find_record_by_id(self.current_view_id)
		if not rec:
			return
		try:
			tags = self.db.get_media_tags(int(rec.id))
		except Exception:
			tags = []
		if not tags:
			lbl = ttk.Label(self.tagging_tags_frame, text='No tags yet', style='Muted.TLabel')
			lbl.pack(anchor='w')
			return
		row = ttk.Frame(self.tagging_tags_frame, style='App.TFrame')
		row.pack(fill='x')
		for t in tags:
			chip = ttk.Label(row, text=f' {t} ', style='Tag.TLabel')
			chip.pack(side='left', padx=3, pady=1)

	def _on_tagging_entry_key(self, event: tk.Event):  # type: ignore[override]
		# Prevent nav keys from inserting characters while the entry is focused
		try:
			k = (event.char or '').lower()
			ks = (event.keysym or '').lower()
			if k in [self.tag_prev_key, self.tag_next_key]:
				self._navigate(-1 if k == self.tag_prev_key else 1)
				self._update_tagging_image()
				return 'break'
			if ks in ['left', 'right']:
				self._navigate(-1 if ks == 'left' else 1)
				self._update_tagging_image()
				return 'break'
		except Exception:
			return None
		return None

	def _on_tagging_entry_nav(self, direction: str):  # bound via lambda
		try:
			if direction == 'left':
				self._navigate(-1)
			else:
				self._navigate(1)
			self._update_tagging_image()
			return 'break'
		except Exception:
			return 'break'

	def _ensure_tag_suggest_window(self) -> None:
		# Create the lightweight popup and listbox if needed
		if self._tag_suggest_window and self._tag_suggest_list:
			return
		try:
			win = tk.Toplevel(self.root)
			win.overrideredirect(True)
			try:
				win.attributes('-topmost', True)
			except Exception:
				pass
			# Prevent taking focus from the entry
			win.transient(self.root)
			# Listbox for suggestions
			lb = tk.Listbox(win, height=8, activestyle='dotbox', exportselection=False)
			# Simple theming
			try:
				lb.configure(
					background=self.palette.get('card_bg', '#ffffff'),
					foreground=self.palette.get('text', '#111827'),
					selectbackground=self.palette.get('selected_bg', '#2563eb'),
					selectforeground='#ffffff'
				)
			except Exception:
				pass
			lb.pack(fill='both', expand=True)
			# Mouse interactions
			lb.bind('<Button-1>', self._on_tag_suggest_click)
			lb.bind('<Double-Button-1>', self._on_tag_suggest_double_click)
			self._tag_suggest_window = win
			self._tag_suggest_list = lb
		except Exception:
			self._tag_suggest_window = None
			self._tag_suggest_list = None

	def _place_tag_suggest_window(self) -> None:
		# Position the popup just under the tagging entry
		if not (self._tag_suggest_window and self.tagging_entry):
			return
		try:
			self.tagging_entry.update_idletasks()
			self._tag_suggest_window.update_idletasks()
			# Desired geometry
			entry_x = int(self.tagging_entry.winfo_rootx())
			entry_y = int(self.tagging_entry.winfo_rooty())
			entry_h = int(self.tagging_entry.winfo_height())
			w = int(max(160, self.tagging_entry.winfo_width()))
			# Preferred: below the entry
			x = entry_x
			y = entry_y + entry_h
			# Compute required height; clamp to screen if needed
			screen_w = int(self.root.winfo_screenwidth())
			screen_h = int(self.root.winfo_screenheight())
			try:
				req_h = int(self._tag_suggest_window.winfo_reqheight()) or 200
			except Exception:
				req_h = 200
			# If it would overflow bottom, try placing above
			if y + req_h > screen_h - 10:
				y = max(0, entry_y - req_h)
			# Clamp x so it stays on screen
			if x + w > screen_w - 10:
				x = max(0, screen_w - w - 10)
			x = max(0, x)
			y = max(0, y)
			self._tag_suggest_window.geometry(f"{w}x{req_h}+{x}+{y}")
		except Exception:
			pass

	def _hide_tag_suggestions(self) -> None:
		try:
			if self._tag_suggest_window is not None:
				try:
					self._tag_suggest_window.destroy()
				except Exception:
					pass
		finally:
			self._tag_suggest_window = None
			self._tag_suggest_list = None
			self._tag_suggest_items = []

	def _on_tagging_entry_change(self, event: tk.Event) -> None:
		# Update suggestions based on current text
		try:
			if not self.tagging_mode:
				self._hide_tag_suggestions()
				return
			text = (self.tag_input_var.get() or '').strip().lower()
			if not text:
				self._hide_tag_suggestions()
				return
			# Fetch all tags and filter by prefix
			try:
				all_tags = self.db.all_tags()
			except Exception:
				all_tags = []
			matches = [t for t in all_tags if isinstance(t, str) and t.startswith(text)]
			# Avoid showing only exact match
			if len(matches) == 1 and matches[0] == text:
				self._hide_tag_suggestions()
				return
			matches = matches[:20]
			if not matches:
				self._hide_tag_suggestions()
				return
			self._ensure_tag_suggest_window()
			if not (self._tag_suggest_window and self._tag_suggest_list):
				return
			self._tag_suggest_items = matches
			# Adjust list height to number of items (max ~8)
			try:
				self._tag_suggest_list.configure(height=min(len(matches), 8))
			except Exception:
				pass
			self._tag_suggest_list.delete(0, tk.END)
			for m in matches:
				self._tag_suggest_list.insert(tk.END, m)
			# Select first item by default
			if matches:
				try:
					self._tag_suggest_list.selection_clear(0, tk.END)
					self._tag_suggest_list.selection_set(0)
					self._tag_suggest_list.activate(0)
				except Exception:
					pass
			self._place_tag_suggest_window()
			try:
				self._tag_suggest_window.deiconify()
			except Exception:
				pass
		except Exception:
			self._hide_tag_suggestions()
		# Do not propagate further
		return None

	def _on_tagging_return(self, event: tk.Event):
		# If suggestions visible, accept current suggestion into the entry (no add yet)
		try:
			if self._tag_suggest_window and self._tag_suggest_list and self._tag_suggest_items:
				sel = self._tag_suggest_list.curselection()
				idx = int(sel[0]) if sel else 0
				if 0 <= idx < len(self._tag_suggest_items):
					selected = str(self._tag_suggest_items[idx])
					current = (self.tag_input_var.get() or '').strip().lower()
					# Only replace if it would change the text
					if selected and selected != current:
						self.tag_input_var.set(selected)
						try:
							self.tagging_entry.icursor(tk.END)
						except Exception:
							pass
						self._hide_tag_suggestions()
						return 'break'
		except Exception:
			pass
		# Otherwise, perform the normal add
		self._on_tagging_enter(event)
		return 'break'

	def _on_tag_suggest_down(self, event: tk.Event):
		# Move selection down in suggestion list
		if not self._tag_suggest_list:
			return None
		try:
			sel = self._tag_suggest_list.curselection()
			idx = int(sel[0]) if sel else -1
			idx = min(idx + 1, max(0, len(self._tag_suggest_items) - 1))
			self._tag_suggest_list.selection_clear(0, tk.END)
			self._tag_suggest_list.selection_set(idx)
			self._tag_suggest_list.activate(idx)
			return 'break'
		except Exception:
			return 'break'

	def _on_tag_suggest_up(self, event: tk.Event):
		# Move selection up in suggestion list
		if not self._tag_suggest_list:
			return None
		try:
			sel = self._tag_suggest_list.curselection()
			idx = int(sel[0]) if sel else 0
			idx = max(idx - 1, 0)
			self._tag_suggest_list.selection_clear(0, tk.END)
			self._tag_suggest_list.selection_set(idx)
			self._tag_suggest_list.activate(idx)
			return 'break'
		except Exception:
			return 'break'

	def _accept_tag_suggestion(self) -> None:
		if not (self._tag_suggest_list and self._tag_suggest_items):
			return
		try:
			sel = self._tag_suggest_list.curselection()
			idx = int(sel[0]) if sel else 0
			if 0 <= idx < len(self._tag_suggest_items):
				val = str(self._tag_suggest_items[idx])
				self.tag_input_var.set(val)
				try:
					self.tagging_entry.icursor(tk.END)
				except Exception:
					pass
		finally:
			self._hide_tag_suggestions()

	def _on_tag_suggest_accept(self, event: tk.Event):
		# Accept selected suggestion into the entry and keep focus
		self._accept_tag_suggestion()
		return 'break'

	def _on_tag_suggest_click(self, event: tk.Event):
		self._accept_tag_suggestion()
		return 'break'

	def _on_tag_suggest_double_click(self, event: tk.Event):
		self._accept_tag_suggestion()
		return 'break'

	def _add_hotkey_mapping(self) -> None:
		k = (self.hk_new_key_var.get() or '').strip().lower()
		t = (self.hk_new_tag_var.get() or '').strip().lower()
		if not k or not t:
			messagebox.showerror('Hotkeys', 'Please enter both key and tag')
			return
		self.hotkeys[k] = t
		save_hotkeys(self.hotkeys)
		self.hk_new_key_var.set('')
		self.hk_new_tag_var.set('')
		self._render_hotkey_list()
		messagebox.showinfo('Hotkeys', f"Added mapping {k} -> {t}")

	def _remove_hotkey_mapping(self, key: str) -> None:
		tag_to_remove = self.hotkeys.get(key)
		self.hotkeys.pop(key, None)
		save_hotkeys(self.hotkeys)
		# Offer to remove tag globally if it is now unmapped
		try:
			still_mapped = tag_to_remove in set(self.hotkeys.values()) if tag_to_remove else False
		except Exception:
			still_mapped = False
		if tag_to_remove and not still_mapped:
			ans = messagebox.askyesno('Remove Tag Globally?', f"Also remove tag '{tag_to_remove}' from all items?")
			if ans:
				try:
					removed = self.db.remove_tag_globally(tag_to_remove)
					messagebox.showinfo('Tags', f"Removed '{tag_to_remove}' from {removed} item(s)")
					self.refresh_records()
				except Exception:
					pass
		self._render_hotkey_list()

	def _toggle_sidebar_tag(self, key: str, checked: bool) -> None:
		# Toggle applying/removing tag to current selection when checkbox is changed
		tag = self.hotkeys.get(key)
		if not tag:
			return
		if checked:
			self.apply_tag_to_selection(tag)
		else:
			# Explicit remove across selection
			if not self.selected_ids:
				return
			for mid in list(self.selected_ids):
				try:
					self.db.remove_media_tags(int(mid), [tag])
				except Exception:
					pass
			self.refresh_records(preserve_selection=True)

	def toggle_select(self, media_id: int) -> None:
		if media_id in self.selected_ids:
			self.selected_ids.remove(media_id)
		else:
			self.selected_ids.add(media_id)
		# Update selection anchor on normal click toggles
		try:
			self._selection_anchor_id = int(media_id)
		except Exception:
			self._selection_anchor_id = media_id
		# Update the specific frame background
		for child in self.grid_frame.winfo_children():
			# child is a frame containing a label named with file name; we stored no ids, so check text widget
			# Instead, simply rebuild subtle style by checking labels under frame
			pass
		self._refresh_card_styles()
		# Update viewer when selection changes in viewing mode
		if self.view_mode:
			self.current_view_id = int(media_id)
			self._update_viewer_image()
			self._scroll_selected_into_view()

	def _scroll_selected_into_view(self) -> None:
		try:
			if not self.view_mode or not self.card_frames:
				return
			# Find index of current_view_id
			idx = 0
			for i, rec in enumerate(self.records):
				if int(rec.id) == int(self.current_view_id or -1):
					idx = i
					break
			frame = self.card_frames[idx]
			self.grid_frame.update_idletasks()
			total_w = max(1, int(self.grid_frame.winfo_width()))
			cw = max(1, int(self.canvas.winfo_width()))
			# Center on frame center
			frame_center = int(frame.winfo_x()) + int(frame.winfo_width() // 2)
			desired_left = max(0, frame_center - (cw // 2))
			if total_w <= cw:
				frac = 0.0
			else:
				frac = desired_left / float(max(1, total_w - cw))
			self.canvas.xview_moveto(min(max(frac, 0.0), 1.0))
		except Exception:
			pass

	def _navigate(self, delta: int) -> None:
		if not self.records:
			return
		# Determine current index; if none, start at 0
		try:
			cur_idx = 0
			for i, rec in enumerate(self.records):
				if int(rec.id) == int(self.current_view_id or -1):
					cur_idx = i
					break
			next_idx = (cur_idx + delta) % len(self.records)
			self.current_view_id = self.records[next_idx].id
			self.selected_ids = {int(self.current_view_id)}
			self._refresh_card_styles()
			self._update_viewer_image()
			self._scroll_selected_into_view()
		except Exception:
			pass

	def _refresh_card_styles(self) -> None:
		# Recolor using cached frame order matching records
		for frame, rec in zip(self.card_frames, self.records):
			self._update_card_style(frame, rec.id)

	def on_key(self, event: tk.Event) -> None:
		# Update last key console
		k = (event.char or '').lower()
		if not k:
			return
		self.last_key_var.set(f'Last key: {k}')
		# If typing in the tagging entry, only allow navigation keys; ignore tag hotkey mappings
		try:
			if self.tagging_mode and getattr(self, 'tagging_entry', None) and (self.tagging_entry.focus_get() is self.tagging_entry):
				if k in [self.tag_prev_key, self.tag_next_key]:
					self._navigate(-1 if k == self.tag_prev_key else 1)
					self._update_tagging_image()
				return
		except Exception:
			pass
		# In viewing mode, A/D navigate
		if self.view_mode and k in ['a', 'd']:
			self._navigate(-1 if k == 'a' else 1)
			return
		# In tagging mode, use assignable keys to navigate
		if self.tagging_mode and k in [self.tag_prev_key, self.tag_next_key]:
			self._navigate(-1 if k == self.tag_prev_key else 1)
			self._update_tagging_image()
			return
		tag = self.hotkeys.get(k)
		if not tag:
			return
		self.apply_tag_to_selection(tag)

	def on_arrow_left(self, event: tk.Event) -> None:
		if self.view_mode or self.tagging_mode:
			self._navigate(-1)
			if self.tagging_mode:
				self._update_tagging_image()

	def on_arrow_right(self, event: tk.Event) -> None:
		if self.view_mode or self.tagging_mode:
			self._navigate(1)
			if self.tagging_mode:
				self._update_tagging_image()

	def on_ctrl_key(self, event: tk.Event) -> None:
		k = (event.keysym or '').lower()
		if k in [str(d) for d in range(0, 10)]:
			combo = f'ctrl+{k}'
			self.last_key_var.set(f'Last key: {combo}')
			# Suppress tag hotkeys while typing in tagging entry
			try:
				if self.tagging_mode and getattr(self, 'tagging_entry', None) and (self.tagging_entry.focus_get() is self.tagging_entry):
					return
			except Exception:
				pass
			tag = self.hotkeys.get(combo)
			if tag:
				self.apply_tag_to_selection(tag)

	def _find_index_by_id(self, media_id: int) -> Optional[int]:
		try:
			mid = int(media_id)
		except Exception:
			mid = media_id
		for i, r in enumerate(self.records):
			try:
				if int(r.id) == int(mid):
					return i
			except Exception:
				if getattr(r, 'id', None) == mid:
					return i
		return None

	def on_item_click(self, event: tk.Event, media_id: int) -> None:
		# Detect modifier keys: Shift (0x0001), Control (0x0004)
		shift_down = False
		ctrl_down = False
		try:
			state_val = int(getattr(event, 'state', 0))
			shift_down = bool(state_val & 0x0001)
			ctrl_down = bool(state_val & 0x0004)
		except Exception:
			shift_down = False
			ctrl_down = False
		# Shift+click: select contiguous range (replace selection)
		if shift_down and self._selection_anchor_id is not None:
			start_idx = self._find_index_by_id(self._selection_anchor_id)
			end_idx = self._find_index_by_id(media_id)
			if start_idx is not None and end_idx is not None:
				lo = min(int(start_idx), int(end_idx))
				hi = max(int(start_idx), int(end_idx))
				try:
					self.selected_ids = {int(r.id) for r in self.records[lo:hi + 1]}
				except Exception:
					self.selected_ids = set(r.id for r in self.records[lo:hi + 1])
				self._refresh_card_styles()
				# In viewing mode, update viewer to clicked item
				if self.view_mode:
					try:
						self.current_view_id = int(media_id)
					except Exception:
						self.current_view_id = media_id
					self._update_viewer_image()
					self._scroll_selected_into_view()
				# Update anchor to the last clicked endpoint
				try:
					self._selection_anchor_id = int(media_id)
				except Exception:
					self._selection_anchor_id = media_id
				return
		# Ctrl+click: toggle item without affecting other selections
		if ctrl_down:
			self.toggle_select(media_id)
			try:
				self._selection_anchor_id = int(media_id)
			except Exception:
				self._selection_anchor_id = media_id
			return
		# Plain click: select only this item
		try:
			mid_int = int(media_id)
		except Exception:
			mid_int = media_id  # type: ignore[assignment]
		self.selected_ids = {mid_int} if isinstance(mid_int, int) else {media_id}
		self._refresh_card_styles()
		# Update viewer to clicked item in viewing mode
		if self.view_mode:
			try:
				self.current_view_id = int(media_id)
			except Exception:
				self.current_view_id = media_id
			self._update_viewer_image()
			self._scroll_selected_into_view()
		# Update anchor
		try:
			self._selection_anchor_id = int(media_id)
		except Exception:
			self._selection_anchor_id = media_id

	def _show_toast(self, text: str, start_delay_ms: int = 900, fade_step_ms: int = 60, start_alpha: float = 0.95, step_delta: float = 0.08) -> None:
		# Destroy any existing toast so we only show the latest
		try:
			if getattr(self, '_toast_window', None) is not None:
				try:
					self._toast_window.destroy()  # type: ignore[union-attr]
				except Exception:
					pass
				self._toast_window = None
		except Exception:
			self._toast_window = None
		# Create borderless, topmost window that won't steal focus
		toast = tk.Toplevel(self.root)
		self._toast_window = toast
		try:
			toast.overrideredirect(True)
			toast.attributes('-alpha', float(start_alpha))
			toast.attributes('-topmost', True)
		except Exception:
			pass
		# Content
		bg = self.palette.get('tag_bg', '#1e293b')
		fg = self.palette.get('tag_fg', '#93c5fd')
		frm = tk.Frame(toast, bg=bg, bd=0, highlightthickness=0)
		frm.pack(fill='both', expand=True)
		lbl = tk.Label(frm, text=text, bg=bg, fg=fg, padx=12, pady=8)
		lbl.pack()
		# Size and position (bottom-right of root)
		try:
			toast.update_idletasks()
			root_x = int(self.root.winfo_rootx())
			root_y = int(self.root.winfo_rooty())
			root_w = int(self.root.winfo_width())
			root_h = int(self.root.winfo_height())
			win_w = int(toast.winfo_reqwidth())
			win_h = int(toast.winfo_reqheight())
			x = root_x + max(0, root_w - win_w - 24)
			y = root_y + max(0, root_h - win_h - 24)
			toast.geometry(f"{win_w}x{win_h}+{x}+{y}")
		except Exception:
			pass
		# Keep focus on the main window (avoid toast stealing input)
		try:
			self.root.focus_force()
		except Exception:
			pass
		# Fade-out sequence
		def _fade(step: int = 0) -> None:
			# If a newer toast replaced this one, stop
			if toast is not getattr(self, '_toast_window', None):
				try:
					toast.destroy()
				except Exception:
					pass
				return
			alpha = max(0.0, float(start_alpha) - float(step) * float(step_delta))
			try:
				toast.attributes('-alpha', alpha)
			except Exception:
				pass
			if alpha <= 0.02:
				try:
					toast.destroy()
				except Exception:
					pass
				if getattr(self, '_toast_window', None) is toast:
					self._toast_window = None
				return
			try:
				toast.after(int(fade_step_ms), lambda: _fade(step + 1))
			except Exception:
				pass
		try:
			toast.after(int(start_delay_ms), _fade)
		except Exception:
			# If scheduling fails, destroy immediately
			try:
				toast.destroy()
			except Exception:
				pass
			self._toast_window = None

	def apply_tag_to_selection(self, tag: str) -> None:
		if not self.selected_ids:
			return
		# Toggle: if item already has the tag, remove it; otherwise add it
		changed_add = 0
		changed_remove = 0
		for mid in list(self.selected_ids):
			try:
				existing = set(self.db.get_media_tags(int(mid)))
				if tag in existing:
					self.db.remove_media_tags(int(mid), [tag])
					changed_remove += 1
				else:
					self.db.add_media_tags(int(mid), [tag])
					changed_add += 1
			except Exception:
				pass
		# Immediately refresh the grid so tag changes are visible; preserve selection
		self.refresh_records(preserve_selection=True)
		if changed_add and not changed_remove:
			self._show_toast(f"Added '{tag}' to {changed_add} item(s)")
		elif changed_remove and not changed_add:
			self._show_toast(f"Removed '{tag}' from {changed_remove} item(s)")
		else:
			self._show_toast(f"Added '{tag}' to {changed_add}, removed from {changed_remove}")

	def open_hotkey_settings(self) -> None:
		# Deprecated: hotkeys are managed in the left panel now.
		dialog = tk.Toplevel(self.root)
		dialog.title('Hotkey Settings (deprecated)')
		dialog.grab_set()
		frame = ttk.Frame(dialog, padding=12)
		frame.pack(fill='both', expand=True)
		lbl = ttk.Label(frame, text='Manage hotkeys in the left panel.', style='Muted.TLabel')
		lbl.pack()
		btn = ttk.Button(frame, text='Close', command=dialog.destroy)
		btn.pack(pady=8)


if __name__ == '__main__':
	root = tk.Tk()
	app = KeyTaggerApp(root)
	root.mainloop()
