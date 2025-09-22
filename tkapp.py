import os
import json
import threading
from typing import Dict, List, Optional, Set, Tuple
import sys

from PIL import Image, ImageTk
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
		self.photo_cache: Dict[int, ImageTk.PhotoImage] = {}
		self.records: List[MediaRecord] = []
		self.card_frames: List[ttk.Frame] = []
		self._cols: int = 1
		self._thumb_px: int = THUMB_SIZE

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
		side.grid(row=0, column=0, sticky='ns')

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

		# Main area with scrollable canvas
		main = ttk.Frame(self.root, style='App.TFrame')
		main.grid(row=0, column=1, sticky='nsew')
		main.rowconfigure(0, weight=1)
		main.columnconfigure(0, weight=1)

		self.canvas = tk.Canvas(main, highlightthickness=0, background=self.palette.get('canvas_bg', '#f6f7fb'))
		scroll_y = ttk.Scrollbar(main, orient='vertical', command=self.canvas.yview)
		self.grid_frame = ttk.Frame(self.canvas, style='App.TFrame')
		self.grid_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
		self.grid_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor='nw')
		self.canvas.configure(yscrollcommand=scroll_y.set)
		self.canvas.grid(row=0, column=0, sticky='nsew')
		scroll_y.grid(row=0, column=1, sticky='ns')
		self.canvas.bind('<Configure>', self._on_canvas_configure)

		# Enable mouse-wheel scrolling globally so it works over all child widgets
		self._activate_mousewheel()

		# Apply app background
		self.root.configure(background=self.palette.get('root_bg', '#e9edf5'))

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
				'selected_bg': '#0b253c',
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
				'selected_bg': '#e7f0ff',
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
			self.canvas.itemconfigure(self.grid_window, width=event.width)
		except Exception:
			pass
		# Recompute desired number of columns based on available width
		new_cols = self._compute_columns(max(1, int(event.width)))
		if new_cols != self._cols:
			self._cols = new_cols
			self._layout_cards()

	def _compute_columns(self, available_width: int) -> int:
		# Approximate per-card width: thumbnail + frame padding + grid padding
		pad = 6 * 2  # left/right grid padding aggregate
		frame_pad = 8 * 2  # left/right internal padding
		card_w = THUMB_SIZE + pad + frame_pad
		return max(1, available_width // max(1, card_w))

	def _layout_cards(self) -> None:
		cols = max(1, self._cols)
		pad = 6
		for idx, frame in enumerate(self.card_frames):
			row = idx // cols
			col = idx % cols
			frame.grid_configure(row=row, column=col, padx=pad, pady=pad, sticky='n')
		self.grid_frame.update_idletasks()
		self.canvas.configure(scrollregion=self.canvas.bbox('all'))

	def _bind_hotkeys(self) -> None:
		self.root.bind('<Key>', self.on_key)
		self.root.bind('<Control-KeyPress>', self.on_ctrl_key)

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

	def refresh_records(self) -> None:
		root_dir = self.folder_var.get().strip() or None
		try:
			records, total = self.db.query_media(required_tags=None, search_text=None, limit=500, offset=0, root_dir=root_dir)
		except TypeError:
			records, total = self.db.query_media(required_tags=None, search_text=None, limit=500, offset=0)
			if root_dir:
				records = [r for r in records if os.path.abspath(r.root_dir) == os.path.abspath(root_dir)]
		self.records = records
		self.selected_ids.clear()
		for w in self.grid_frame.winfo_children():
			w.destroy()
		self.photo_cache.clear()
		self._render_grid()

	def _render_grid(self) -> None:
		cols = max(1, self._cols)
		pad = 6
		self.card_frames = []
		for idx, rec in enumerate(self.records):
			row = idx // cols
			col = idx % cols
			frame = ttk.Frame(self.grid_frame, padding=8, style='Card.TFrame')
			frame.grid(row=row, column=col, padx=pad, pady=pad, sticky='n')
			frame.bind('<Button-1>', lambda e, rid=rec.id: self.toggle_select(rid))
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

			# Select button (square) top-left
			btn = ttk.Button(frame, text='■', width=2, command=lambda rid=rec.id: self.toggle_select(rid), style='Small.TButton')
			btn.grid(row=0, column=0, sticky='nw')

			thumb_path = rec.thumbnail_path if rec.thumbnail_path and os.path.exists(rec.thumbnail_path) else None
			if not thumb_path and rec.file_path and os.path.exists(rec.file_path):
				thumb_path = build_square_thumbnail(rec.file_path)
				if thumb_path:
					self.db.update_thumbnail_path(rec.file_path, thumb_path)

			img_label = ttk.Label(frame)
			img_label.grid(row=1, column=0, padx=0, pady=0)
			if thumb_path and os.path.exists(thumb_path):
				try:
					pil_im = Image.open(thumb_path)
					photo = ImageTk.PhotoImage(pil_im)
					self.photo_cache[rec.id] = photo
					img_label.configure(image=photo)
					# Keep a direct reference on the widget to avoid garbage collection
					img_label.image = photo
				except Exception:
					pass

			name_label = ttk.Label(frame, text=rec.file_name, width=40, wraplength=max(120, THUMB_SIZE), justify='center')
			name_label.grid(row=2, column=0, padx=0, pady=(4, 0))

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

	def _update_card_style(self, frame: ttk.Frame, media_id: int) -> None:
		selected = media_id in self.selected_ids
		style = ttk.Style()
		style_name = f'Card{media_id}.TFrame'
		style.configure(style_name, background=(self.palette.get('selected_bg', '#e7f0ff') if selected else self.palette.get('card_bg', '#ffffff')))
		frame.configure(style=style_name)

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
			self.refresh_records()

	def toggle_select(self, media_id: int) -> None:
		if media_id in self.selected_ids:
			self.selected_ids.remove(media_id)
		else:
			self.selected_ids.add(media_id)
		# Update the specific frame background
		for child in self.grid_frame.winfo_children():
			# child is a frame containing a label named with file name; we stored no ids, so check text widget
			# Instead, simply rebuild subtle style by checking labels under frame
			pass
		self._refresh_card_styles()

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
		tag = self.hotkeys.get(k)
		if not tag:
			return
		self.apply_tag_to_selection(tag)

	def on_ctrl_key(self, event: tk.Event) -> None:
		k = (event.keysym or '').lower()
		if k in [str(d) for d in range(0, 10)]:
			combo = f'ctrl+{k}'
			self.last_key_var.set(f'Last key: {combo}')
			tag = self.hotkeys.get(combo)
			if tag:
				self.apply_tag_to_selection(tag)

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
		# Immediately refresh the grid so tag changes are visible
		self.refresh_records()
		if changed_add and not changed_remove:
			messagebox.showinfo('Tag Applied', f"Added '{tag}' to {changed_add} item(s)")
		elif changed_remove and not changed_add:
			messagebox.showinfo('Tag Removed', f"Removed '{tag}' from {changed_remove} item(s)")
		else:
			messagebox.showinfo('Tags Updated', f"Added '{tag}' to {changed_add}, removed from {changed_remove}")

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
