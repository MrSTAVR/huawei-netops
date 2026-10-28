"""Тема оформления: палитра, шрифты, стили ttk и мелкие переиспользуемые виджеты."""
import tkinter as tk
from tkinter import ttk

BG = "#F4F6FA"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8F9FC"
BORDER = "#E3E7EE"
TEXT = "#1B2230"
MUTED = "#6B7385"
ACCENT = "#2F5BEA"
ACCENT_HOVER = "#2449C4"
ACCENT_SOFT = "#E8EEFF"
DANGER = "#D64545"
DANGER_SOFT = "#FDECEC"
SUCCESS = "#1F9D55"

SIDEBAR = "#161B26"
SIDEBAR_HOVER = "#20273A"
SIDEBAR_ACTIVE = "#2A3247"
SIDEBAR_TEXT = "#AEB6C8"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI Semibold", 17)
FONT_H2 = ("Segoe UI Semibold", 12)
FONT_MONO = ("Consolas", 10)


def enable_dpi_awareness():
    """Чёткий текст на Windows с масштабированием экрана (иначе tkinter размыт)."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def apply(root):
    root.configure(bg=BG)
    # Именованные шрифты, а не option_add("*Font"): опция перебивает шрифты из стилей ttk
    from tkinter import font as tkfont
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name).configure(family=FONT[0], size=FONT[1])
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*Menu.font", FONT)

    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".", background=BG, foreground=TEXT, font=FONT, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, focuscolor=ACCENT, troughcolor=BG)

    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=SURFACE)

    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=SURFACE)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED, font=FONT_SMALL)
    s.configure("Title.TLabel", font=FONT_TITLE)
    s.configure("Subtitle.TLabel", foreground=MUTED)
    s.configure("CardTitle.TLabel", background=SURFACE, font=FONT_H2)
    s.configure("Error.TLabel", background=SURFACE, foreground=DANGER, font=FONT_SMALL)
    s.configure("Status.TLabel", background=BG, foreground=MUTED, font=FONT_SMALL)

    # Кнопки
    s.configure("TButton", background=SURFACE, foreground=TEXT, padding=(14, 6),
                relief="flat", borderwidth=1, bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE)
    s.map("TButton",
          background=[("pressed", BORDER), ("active", SURFACE_ALT)],
          bordercolor=[("focus", ACCENT), ("active", "#C9CFDA")])
    s.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", bordercolor=ACCENT,
                lightcolor=ACCENT, darkcolor=ACCENT, font=FONT_BOLD)
    s.map("Accent.TButton",
          background=[("disabled", "#A9B9EE"), ("pressed", ACCENT_HOVER), ("active", ACCENT_HOVER)],
          bordercolor=[("active", ACCENT_HOVER)])
    s.configure("Danger.TButton", foreground=DANGER)
    s.map("Danger.TButton", background=[("active", DANGER_SOFT)], bordercolor=[("active", DANGER)])

    # Поля ввода
    for widget in ("TEntry", "TCombobox"):
        s.configure(widget, fieldbackground=SURFACE, background=SURFACE, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE, padding=6,
                    insertcolor=TEXT, arrowcolor=MUTED)
        s.map(widget, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", SURFACE)])
    # В clam у readonly-комбобокса в фокусе текст выделяется — белым по белому
    s.map("TCombobox", selectbackground=[("readonly", SURFACE)], selectforeground=[("readonly", TEXT)],
          foreground=[("readonly", TEXT)])

    # Переключатели
    for widget in ("TCheckbutton", "TRadiobutton"):
        s.configure(widget, background=SURFACE, foreground=TEXT, indicatorcolor=SURFACE,
                    indicatorbackground=SURFACE)
        s.map(widget, background=[("active", SURFACE)],
              indicatorcolor=[("selected", ACCENT), ("pressed", ACCENT_SOFT)])

    # Сегментированный переключатель (radiobutton без индикатора)
    s.configure("Segment.Toolbutton", background=SURFACE_ALT, foreground=MUTED, padding=(12, 5),
                bordercolor=BORDER, lightcolor=SURFACE_ALT, darkcolor=SURFACE_ALT, relief="flat")
    s.map("Segment.Toolbutton",
          background=[("selected", ACCENT_SOFT), ("active", BORDER)],
          foreground=[("selected", ACCENT)],
          bordercolor=[("selected", ACCENT)])

    # Таблицы
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                rowheight=30, borderwidth=0, relief="flat")
    s.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
    s.configure("Treeview.Heading", background=SURFACE_ALT, foreground=MUTED, font=FONT_BOLD,
                relief="flat", borderwidth=0, padding=(8, 6))
    s.map("Treeview.Heading", background=[("active", BORDER)])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # Скроллбары
    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background="#D3D8E1", troughcolor=SURFACE,
                    bordercolor=SURFACE, lightcolor="#D3D8E1", darkcolor="#D3D8E1",
                    arrowcolor=MUTED, gripcount=0, arrowsize=12)
        s.map(f"{orient}.TScrollbar", background=[("active", "#B7BFCC")])

    s.configure("TPanedwindow", background=BG)
    s.configure("Sash", sashthickness=8, background=BG, gripcount=0)


def card(parent, padding=16):
    """Белая карточка с тонкой рамкой. Возвращает (внешний фрейм, внутренний ttk.Frame)."""
    outer = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
    inner = ttk.Frame(outer, style="Card.TFrame", padding=padding)
    inner.pack(fill=tk.BOTH, expand=True)
    return outer, inner


def style_text(widget, mono=True):
    widget.configure(bg=SURFACE, fg=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                     font=FONT_MONO if mono else FONT, padx=12, pady=10, wrap=tk.NONE,
                     insertbackground=TEXT, selectbackground=ACCENT_SOFT, selectforeground=TEXT)


def scrolled(parent, widget_factory, horizontal=False):
    """Создаёт виджет с вертикальным (и опционально горизонтальным) скроллбаром в grid-контейнере."""
    frame = ttk.Frame(parent, style="Card.TFrame")
    widget = widget_factory(frame)
    widget.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=widget.yview)
    vsb.grid(row=0, column=1, sticky="ns")
    widget.configure(yscrollcommand=vsb.set)
    if horizontal:
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=widget.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        widget.configure(xscrollcommand=hsb.set)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, widget


class PlaceholderEntry(ttk.Entry):
    """Поле ввода с серой подсказкой, пока оно пустое."""

    def __init__(self, parent, placeholder, textvariable=None, **kw):
        self.var = textvariable or tk.StringVar()
        super().__init__(parent, textvariable=self.var, **kw)
        self.placeholder = placeholder
        self._showing = False
        self.bind("<FocusIn>", self._hide)
        self.bind("<FocusOut>", self._show)
        self._show()

    def _show(self, _=None):
        if not self.var.get():
            self._showing = True
            self.configure(foreground=MUTED)
            self.var.set(self.placeholder)

    def _hide(self, _=None):
        if self._showing:
            self._showing = False
            self.configure(foreground=TEXT)
            self.var.set("")

    def value(self):
        return "" if self._showing else self.var.get().strip()

    def set_value(self, value):
        self._hide()
        self.var.set(value)
        if not value and self.focus_get() is not self:
            self._show()


class CheckList(ttk.Frame):
    """Список с галочками на базе Treeview. on_change вызывается при любом переключении."""

    ON, OFF = "☑", "☐"

    def __init__(self, parent, title, on_change=None, height=8):
        super().__init__(parent, style="Card.TFrame")
        self.on_change = on_change
        self.checked = set()
        self.labels = {}

        head = ttk.Frame(self, style="Card.TFrame")
        head.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side=tk.LEFT)
        self.count_label = ttk.Label(head, style="CardMuted.TLabel")
        self.count_label.pack(side=tk.LEFT, padx=8)
        toggle = ttk.Label(head, text="выбрать все", style="CardMuted.TLabel", cursor="hand2", foreground=ACCENT)
        toggle.pack(side=tk.RIGHT)
        toggle.bind("<Button-1>", lambda e: self.toggle_all())

        frame, self.tree = scrolled(self, lambda p: ttk.Treeview(p, show="tree", selectmode="none", height=height))
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.column("#0", width=300, stretch=True)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", self._on_space)

    def set_items(self, items):
        """items: [(key, label)]. Сохраняет отметки у ключей, которые остались."""
        self.tree.delete(*self.tree.get_children())
        self.labels = dict(items)
        self.checked &= set(self.labels)
        for key, label in items:
            self.tree.insert("", tk.END, iid=str(key), text=self._text(key))
        self._update_count()

    def _text(self, key):
        return f"{self.ON if key in self.checked else self.OFF}   {self.labels[key]}"

    def _key(self, iid):
        return next(k for k in self.labels if str(k) == iid)

    def _toggle(self, iid):
        key = self._key(iid)
        self.checked ^= {key}
        self.tree.item(iid, text=self._text(key))
        self._changed()

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.focus(iid)
            self._toggle(iid)

    def _on_space(self, _):
        if self.tree.focus():
            self._toggle(self.tree.focus())

    def toggle_all(self):
        self.checked = set() if self.checked == set(self.labels) else set(self.labels)
        for key in self.labels:
            self.tree.item(str(key), text=self._text(key))
        self._changed()

    def _changed(self):
        self._update_count()
        if self.on_change:
            self.on_change()

    def _update_count(self):
        self.count_label.configure(text=f"{len(self.checked)} из {len(self.labels)}")

    def selected(self):
        return [k for k in self.labels if k in self.checked]
