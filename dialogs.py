"""Модальные формы добавления/редактирования. Одна универсальная форма вместо пачки однотипных диалогов."""
import ipaddress
import tkinter as tk
from tkinter import ttk

import theme


class FormDialog:
    """
    fields: список словарей:
      key, label, kind ('entry' | 'combo' | 'text'), required (bool, по умолчанию True),
      values ([(value, label)] для combo), hint (серый текст под полем), readonly (bool),
      wide (bool) — на всю ширину при columns > 1
    validate(result) -> строка ошибки или None.
    После закрытия: self.result — dict или None (отмена).
    """

    def __init__(self, parent, title, fields, initial=None, validate=None, ok_text="Сохранить", columns=1):
        self.result = None
        self.fields = fields
        self.validate = validate
        self.widgets = {}
        initial = initial or {}

        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.configure(bg=theme.SURFACE)
        self.top.transient(parent.winfo_toplevel())
        self.top.resizable(False, False)

        body = ttk.Frame(self.top, style="Card.TFrame", padding=(24, 20, 24, 8))
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=title, style="CardTitle.TLabel").grid(row=0, column=0, columnspan=columns,
                                                                    sticky="w", pady=(0, 14))
        for c in range(columns):
            body.columnconfigure(c, weight=1, uniform="col")

        # Каждое поле — ячейка (подпись, виджет, подсказка). Поле с "wide" занимает всю строку.
        row, col = 1, 0
        for field in fields:
            wide = field.get("wide") or columns == 1
            if wide and col:
                row, col = row + 1, 0
            cell = ttk.Frame(body, style="Card.TFrame")
            cell.grid(row=row, column=col, columnspan=columns if wide else 1, sticky="ew",
                      padx=(0 if col == 0 else 8, 0 if wide or col == columns - 1 else 8), pady=(0, 10))
            cell.columnconfigure(0, weight=1)
            label = field["label"] + ("" if field.get("required", True) else "  (необязательно)")
            ttk.Label(cell, text=label, style="Card.TLabel").grid(row=0, column=0, sticky="w")
            widget = self._make_widget(cell, field, initial.get(field["key"]))
            widget.grid(row=1, column=0, sticky="ew", pady=(4, 2))
            self.widgets[field["key"]] = widget
            if field.get("hint"):
                ttk.Label(cell, text=field["hint"], style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
            col += columns if wide else 1
            if col >= columns:
                row, col = row + 1, 0

        self.error = ttk.Label(body, style="Error.TLabel", wraplength=380 * columns)
        self.error.grid(row=row + 1, column=0, columnspan=columns, sticky="w")

        buttons = ttk.Frame(self.top, style="Card.TFrame", padding=(24, 8, 24, 20))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text=ok_text, style="Accent.TButton", command=self._ok).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Отмена", command=self.top.destroy).pack(side=tk.RIGHT, padx=8)

        self.top.bind("<Return>", self._on_return)
        self.top.bind("<Escape>", lambda e: self.top.destroy())

        self._center(parent)
        self.top.grab_set()
        first = next((w for f, w in zip(fields, self.widgets.values()) if not f.get("readonly")), None)
        if first:
            first.focus_set()
        parent.wait_window(self.top)

    def _make_widget(self, parent, field, value):
        kind = field.get("kind", "entry")
        if kind == "combo":
            options = field["values"]
            widget = ttk.Combobox(parent, state="readonly", width=28, values=[lbl for _, lbl in options])
            idx = next((i for i, (v, _) in enumerate(options) if v == value), 0 if options else None)
            if idx is not None:
                widget.current(idx)
            widget.options = options
            return widget
        if kind == "text":
            widget = tk.Text(parent, height=5, width=44, wrap=tk.WORD)
            theme.style_text(widget, mono=True)
            widget.configure(wrap=tk.WORD, highlightthickness=1, highlightbackground=theme.BORDER,
                             highlightcolor=theme.ACCENT, padx=8, pady=6)
            if value:
                widget.insert("1.0", value)
            return widget
        widget = ttk.Entry(parent, width=30)
        if value is not None:
            widget.insert(0, str(value))
        if field.get("readonly"):
            widget.configure(state="readonly")
        return widget

    def _center(self, parent):
        self.top.update_idletasks()
        master = parent.winfo_toplevel()
        x = master.winfo_rootx() + (master.winfo_width() - self.top.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.top.winfo_height()) // 3
        self.top.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _on_return(self, event):
        # В многострочном поле Enter — перевод строки, а не сохранение
        if isinstance(event.widget, tk.Text):
            return
        self._ok()

    def _value(self, field):
        widget = self.widgets[field["key"]]
        kind = field.get("kind", "entry")
        if kind == "combo":
            idx = widget.current()
            return widget.options[idx][0] if idx >= 0 else None
        if kind == "text":
            return widget.get("1.0", tk.END).strip()
        return widget.get().strip()

    def _ok(self):
        result = {}
        for field in self.fields:
            value = self._value(field)
            if field.get("required", True) and value in ("", None):
                self._fail(f"Заполните поле «{field['label']}».", field)
                return
            result[field["key"]] = value if value != "" else None
        if self.validate:
            error = self.validate(result)
            if error:
                self._fail(error)
                return
        self.result = result
        self.top.destroy()

    def _fail(self, message, field=None):
        self.error.configure(text=message)
        if field:
            self.widgets[field["key"]].focus_set()


# ---------- Валидаторы ----------

def _check_ip(value, label="IP"):
    if value is None:
        return None
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return f"{label}: «{value}» — не IPv4-адрес."
    return None


def _check_vlan(result):
    try:
        vlan_id = int(result["vlan_id"])
    except ValueError:
        return "VLAN ID должен быть числом."
    if not 1 <= vlan_id <= 4094:
        return "VLAN ID должен быть в диапазоне 1–4094."
    result["vlan_id"] = vlan_id
    return None


def split_interfaces(raw):
    """'GE1/0/1, GE1/0/2\\nGE1/0/3' -> список, без пустых и дублей."""
    seen = []
    for part in (raw or "").replace("\n", ",").replace(";", ",").split(","):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen


# ---------- Конкретные формы ----------

def ask_cluster(parent, initial=None):
    d = FormDialog(parent, "Редактировать кластер" if initial else "Новый кластер",
                   [{"key": "name", "label": "Имя кластера"}], initial)
    return d.result


def ask_core(parent, initial=None):
    d = FormDialog(parent, "Редактировать Core" if initial else "Новый Core-коммутатор",
                   [{"key": "hostname", "label": "Hostname"},
                    {"key": "ip", "label": "IP адрес", "required": False}],
                   initial, validate=lambda r: _check_ip(r["ip"]))
    return d.result


def ask_vlan(parent, initial=None):
    d = FormDialog(parent, "Редактировать VLAN" if initial else "Новый VLAN",
                   [{"key": "vlan_id", "label": "VLAN ID", "readonly": bool(initial), "hint": "1–4094"},
                    {"key": "description", "label": "Описание", "required": False}],
                   initial, validate=_check_vlan)
    return d.result


def ask_switch(parent, clusters, cores, initial=None):
    fields = [
        {"key": "cluster_id", "label": "Кластер", "kind": "combo",
         "values": [(c["id"], c["name"]) for c in clusters]},
        {"key": "type", "label": "Тип", "kind": "combo",
         "values": [("optical", "Оптика (optical)"), ("copper", "Медь (copper)")]},
        {"key": "hostname", "label": "Hostname"},
        {"key": "ip", "label": "IP адрес"},
        {"key": "core_switch_id", "label": "Core-коммутатор", "kind": "combo",
         "values": [(c["id"], c["hostname"]) for c in cores]},
        {"key": "core_interface", "label": "Интерфейс на Core"},
        {"key": "uplink_interface", "label": "Uplink интерфейс", "hint": "например, 100GE1/0/49", "wide": True},
        {"key": "interfaces", "label": "Интерфейсы серверов", "kind": "text", "required": False,
         "hint": "через запятую или с новой строки", "wide": True},
    ]
    title = "Редактировать TOR" if initial and initial.get("id") else "Новый TOR-коммутатор"
    d = FormDialog(parent, title, fields, initial, validate=lambda r: _check_ip(r["ip"]), columns=2)
    if d.result:
        d.result["interfaces"] = split_interfaces(d.result["interfaces"])
    return d.result
