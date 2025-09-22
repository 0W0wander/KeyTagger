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
		self._setup_theme()
		self.db = Database(base_dir='.')
		self.hotkeys: Dict[str, str] = load_hotkeys()
		self.selected_ids: Set[int] = set()
		self.photo_cache: Dict[int, ImageTk.PhotoImage] = {}
		self.records: List[MediaRecord] = []

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
		settings_btn = ttk.Button(side, text='Hotkey Settings', command=self.open_hotkey_settings)
		settings_btn.pack(fill='x', pady=(12, 6))
		self.last_key_var = tk.StringVar(value='Last key: (none)')
		last_key_lbl = ttk.Label(side, textvariable=self.last_key_var, style='Muted.TLabel')
		last_key_lbl.pack(fill='x')

		# Main area with scrollable canvas
		main = ttk.Frame(self.root, style='App.TFrame')
		main.grid(row=0, column=1, sticky='nsew')
		main.rowconfigure(0, weight=1)
		main.columnconfigure(0, weight=1)

		self.canvas = tk.Canvas(main, highlightthickness=0, background='#f6f7fb')
		scroll_y = ttk.Scrollbar(main, orient='vertical', command=self.canvas.yview)
		self.grid_frame = ttk.Frame(self.canvas, style='App.TFrame')
		self.grid_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
		self.canvas.create_window((0, 0), window=self.grid_frame, anchor='nw')
		self.canvas.configure(yscrollcommand=scroll_y.set)
		self.canvas.grid(row=0, column=0, sticky='nsew')
		scroll_y.grid(row=0, column=1, sticky='ns')

		# Enable mouse-wheel scrolling globally so it works over all child widgets
		self._activate_mousewheel()

		# Apply app background
		self.root.configure(background='#e9edf5')

	def _setup_theme(self) -> None:
		style = ttk.Style()
		try:
			style.theme_use('clam')
		except Exception:
			pass
		# Fonts
		base_font = tkfont.nametofont('TkDefaultFont')
		base_font.configure(family='Segoe UI', size=10)
		title_font = tkfont.nametofont('TkHeadingFont') if 'TkHeadingFont' in tkfont.names() else base_font.copy()
		title_font.configure(family='Segoe UI', size=14, weight='bold')

		# Colors
		bg = '#f6f7fb'
		side_bg = '#ffffff'
		text = '#111827'
		muted = '#6b7280'
		primary = '#2563eb'
		primary_active = '#1d4ed8'
		accent = '#10b981'
		accent_active = '#059669'
		card_bg = '#ffffff'
		selected_bg = '#e7f0ff'
		tag_bg = '#eef2ff'
		tag_fg = '#3730a3'

		# Base styles
		style.configure('App.TFrame', background=bg)
		style.configure('Side.TFrame', background=side_bg)
		style.configure('TLabel', background=side_bg, foreground=text)
		style.configure('Muted.TLabel', background=side_bg, foreground=muted)
		style.configure('Title.TLabel', background=side_bg, foreground=text, font=title_font)

		# Buttons
		style.configure('TButton', padding=(10, 6))
		style.configure('Primary.TButton', background=primary, foreground='#ffffff')
		style.map('Primary.TButton', background=[('active', primary_active), ('pressed', primary_active)])
		style.configure('Accent.TButton', background=accent, foreground='#ffffff')
		style.map('Accent.TButton', background=[('active', accent_active), ('pressed', accent_active)])

		# Cards and tags
		style.configure('Card.TFrame', background=card_bg)
		style.configure('Tag.TLabel', background=tag_bg, foreground=tag_fg, padding=(6, 2))

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
		cols = 6
		pad = 6
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
				style.configure(style_name, background='#f3f4f6')
				f.configure(style=style_name)
			def _on_leave(e, rid=rec.id, f=frame):
				self._update_card_style(f, rid)
			frame.bind('<Enter>', _on_enter)
			frame.bind('<Leave>', _on_leave)

			# Select button (square) top-left
			btn = ttk.Button(frame, text='■', width=2, command=lambda rid=rec.id: self.toggle_select(rid))
			btn.grid(row=0, column=0, sticky='nw')

			thumb_path = rec.thumbnail_path if rec.thumbnail_path and os.path.exists(rec.thumbnail_path) else None
			if not thumb_path and rec.file_path and os.path.exists(rec.file_path):
				thumb_path = build_square_thumbnail(rec.file_path)
				if thumb_path:
					self.db.update_thumbnail_path(rec.file_path, thumb_path)

			img_label = ttk.Label(frame)
			img_label.grid(row=1, column=0)
			if thumb_path and os.path.exists(thumb_path):
				try:
					pil_im = Image.open(thumb_path)
					photo = ImageTk.PhotoImage(pil_im)
					self.photo_cache[rec.id] = photo
					img_label.configure(image=photo)
				except Exception:
					pass

			name_label = ttk.Label(frame, text=rec.file_name, width=40)
			name_label.grid(row=2, column=0)

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
		style.configure(style_name, background=('#e7f0ff' if selected else '#ffffff'))
		frame.configure(style=style_name)

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
		# Walk grid and recolor
		idx_map: Dict[int, ttk.Frame] = {}
		for idx, rec in enumerate(self.records):
			row = idx // 6
			col = idx % 6
			# Locate the frame at (row, col)
			for child in self.grid_frame.grid_slaves(row=row, column=col):
				if isinstance(child, ttk.Frame):
					self._update_card_style(child, rec.id)

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
		for mid in list(self.selected_ids):
			try:
				self.db.add_media_tags(int(mid), [tag])
			except Exception:
				pass
		# Immediately refresh the grid so newly applied tags are visible without manual reload
		self.refresh_records()
		messagebox.showinfo('Tag Applied', f"Added '{tag}' to {len(self.selected_ids)} item(s)")

	def open_hotkey_settings(self) -> None:
		dialog = tk.Toplevel(self.root)
		dialog.title('Hotkey Settings')
		dialog.grab_set()

		frame = ttk.Frame(dialog, padding=10)
		frame.pack(fill='both', expand=True)

		# Existing
		row = 0
		for k in sorted(self.hotkeys.keys()):
			ttk.Label(frame, text=f'Key: {k}').grid(row=row, column=0, sticky='w')
			val_var = tk.StringVar(value=self.hotkeys[k])
			entry = ttk.Entry(frame, textvariable=val_var, width=24)
			entry.grid(row=row, column=1, padx=6)
			def save_one(key=k, var=val_var):
				self.hotkeys[key] = var.get().strip().lower()
			btn = ttk.Button(frame, text='Save', command=save_one)
			btn.grid(row=row, column=2, padx=6)
			def remove_one(key=k):
				self.hotkeys.pop(key, None)
				save_hotkeys(self.hotkeys)
				dialog.destroy()
				self.open_hotkey_settings()
			rem = ttk.Button(frame, text='Remove', command=remove_one)
			rem.grid(row=row, column=3, padx=6)
			row += 1

		# Add new mapping
		sep = ttk.Separator(frame)
		sep.grid(row=row, column=0, columnspan=4, sticky='ew', pady=8)
		row += 1
		new_key_var = tk.StringVar()
		new_tag_var = tk.StringVar()
		ttk.Label(frame, text='Key').grid(row=row, column=0)
		new_key = ttk.Entry(frame, textvariable=new_key_var, width=8)
		new_key.grid(row=row, column=1, sticky='w')
		row += 1
		ttk.Label(frame, text='Tag').grid(row=row, column=0)
		new_tag = ttk.Entry(frame, textvariable=new_tag_var, width=24)
		new_tag.grid(row=row, column=1, sticky='w')
		row += 1
		def add_mapping() -> None:
			k = (new_key_var.get() or '').strip().lower()
			t = (new_tag_var.get() or '').strip().lower()
			if k and t:
				self.hotkeys[k] = t
				save_hotkeys(self.hotkeys)
				messagebox.showinfo('Hotkeys', f"Added mapping {k} -> {t}")
				dialog.destroy()
				self.open_hotkey_settings()
		add_btn = ttk.Button(frame, text='Add', command=add_mapping)
		add_btn.grid(row=row, column=0, columnspan=2, pady=8)


if __name__ == '__main__':
	root = tk.Tk()
	app = KeyTaggerApp(root)
	root.mainloop()
