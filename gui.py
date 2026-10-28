import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import db
import config_generator
import usg_parser
import excel_export
import dialogs
import theme
from theme import PlaceholderEntry, CheckList, card, scrolled

SETTINGS_FILE = os.path.join(os.path.dirname(db.DB_FILE), "settings.json")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class Page(ttk.Frame):
    """Базовая страница: заголовок, подзаголовок, место под кнопки справа."""

    title = ""
    subtitle = ""

    def __init__(self, parent, app):
        super().__init__(parent, padding=(28, 22, 28, 12))
        self.app = app
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 16))
        texts = ttk.Frame(header)
        texts.pack(side=tk.LEFT)
        ttk.Label(texts, text=self.title, style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(texts, text=self.subtitle, style="Subtitle.TLabel").pack(anchor=tk.W)
        self.actions = ttk.Frame(header)
        self.actions.pack(side=tk.RIGHT, anchor=tk.S)
        self.body = ttk.Frame(self)
        self.body.pack(fill=tk.BOTH, expand=True)

    def action(self, text, command, style="TButton"):
        btn = ttk.Button(self.actions, text=text, command=command, style=style)
        btn.pack(side=tk.RIGHT, padx=(8, 0))
        return btn

    def on_show(self):
        pass


# ======================================================================
#  Сеть
# ======================================================================

class NetworkPage(Page):
    title = "Сеть"
    subtitle = "Core → кластеры → TOR-коммутаторы"

    TYPE_LABELS = {"optical": "оптика", "copper": "медь"}

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.node_data = {}

        self.action("+ TOR", self.add_switch, "Accent.TButton")
        self.action("+ Кластер", self.add_cluster)
        self.action("+ Core", self.add_core)

        paned = ttk.PanedWindow(self.body, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Дерево ---
        left_outer, left = card(paned, padding=12)
        paned.add(left_outer, weight=3)

        top = ttk.Frame(left, style="Card.TFrame")
        top.pack(fill=tk.X, pady=(0, 10))
        # Кнопки пакуются первыми, чтобы поле поиска не отбирало у них место
        ttk.Button(top, text="Удалить", style="Danger.TButton", command=self.delete_selected).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(top, text="Изменить", command=self.edit_selected).pack(side=tk.RIGHT, padx=(8, 0))
        self.search = PlaceholderEntry(top, "Поиск по hostname, IP, кластеру…")
        self.search.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search.var.trace_add("write", lambda *_: self.refresh())

        frame, self.tree = scrolled(left, lambda p: ttk.Treeview(
            p, columns=("ip", "type"), show="tree headings", selectmode="browse"))
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.heading("#0", text="Объект", anchor=tk.W)
        self.tree.heading("ip", text="IP", anchor=tk.W)
        self.tree.heading("type", text="Тип", anchor=tk.W)
        self.tree.column("#0", width=300, stretch=True)
        self.tree.column("ip", width=140, stretch=False)
        self.tree.column("type", width=90, stretch=False)
        self.tree.tag_configure("core", font=theme.FONT_BOLD)
        self.tree.tag_configure("cluster", foreground=theme.ACCENT)
        self.tree.tag_configure("group", foreground=theme.MUTED)

        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_details())
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Button-3>", self._context_menu)

        # --- Детали ---
        right_outer, right = card(paned, padding=4)
        paned.add(right_outer, weight=2)
        self.details = tk.Text(right, width=40, wrap=tk.WORD, cursor="arrow")
        theme.style_text(self.details, mono=False)
        self.details.configure(wrap=tk.WORD, padx=18, pady=16, tabs=("170",))
        self.details.pack(fill=tk.BOTH, expand=True)
        d = self.details
        d.tag_configure("h1", font=("Segoe UI Semibold", 15), spacing3=2)
        d.tag_configure("badge", foreground=theme.ACCENT, font=theme.FONT_SMALL, spacing3=12)
        d.tag_configure("key", foreground=theme.MUTED)
        d.tag_configure("section", font=theme.FONT_BOLD, spacing1=14, spacing3=6)
        d.tag_configure("mono", font=theme.FONT_MONO)
        d.tag_configure("muted", foreground=theme.MUTED)

        self.menu = tk.Menu(self, tearoff=0)

    def on_show(self):
        self.refresh()

    # ---------- Дерево ----------

    def _selected_node(self):
        sel = self.tree.selection()
        return self.node_data.get(sel[0]) if sel else None

    def refresh(self):
        selected = self._selected_node()
        query = self.search.value().lower()
        self.tree.delete(*self.tree.get_children())
        self.node_data.clear()

        switches = db.list_switches()
        clusters = db.list_clusters()

        def matches(*values):
            return not query or any(query in (v or "").lower() for v in values)

        def insert(parent, text, values, node, tags):
            iid = self.tree.insert(parent, tk.END, text=text, values=values, tags=tags, open=True)
            self.node_data[iid] = node
            if node == selected:
                self.tree.selection_set(iid)
                self.tree.see(iid)
            return iid

        for core in db.list_core_switches():
            core_tors = [sw for sw in switches if sw["core_switch_id"] == core["id"]]
            core_hit = matches(core["hostname"], core["ip"])
            by_cluster = {}
            for sw in core_tors:
                if core_hit or matches(sw["hostname"], sw["ip"], sw["cluster_name"]):
                    by_cluster.setdefault((sw["cluster_id"], sw["cluster_name"]), []).append(sw)
            if not core_hit and not by_cluster:
                continue

            core_iid = insert("", f"  {core['hostname']}", (core["ip"] or "", "Core"),
                              ("core", core["id"]), ("core",))
            for (cl_id, cl_name), tors in sorted(by_cluster.items(), key=lambda kv: kv[0][1]):
                cl_iid = insert(core_iid, f"  {cl_name}", ("", f"{len(tors)} TOR"), ("cluster", cl_id), ("cluster",))
                for sw in tors:
                    insert(cl_iid, f"  {sw['hostname']}", (sw["ip"], self.TYPE_LABELS.get(sw["type"], sw["type"])),
                           ("switch", sw["id"]), ("switch",))

        # Кластеры без TOR иначе были бы не видны вовсе
        empty = [c for c in clusters if c["switch_count"] == 0 and matches(c["name"])]
        if empty:
            group = self.tree.insert("", tk.END, text="  Кластеры без TOR", open=True, tags=("group",))
            for cl in empty:
                insert(group, f"  {cl['name']}", ("", "пусто"), ("cluster", cl["id"]), ("cluster",))

        self.app.set_status(f"Core: {len(db.list_core_switches())} · кластеров: {len(clusters)} · TOR: {len(switches)}")
        self.show_details()

    # ---------- Детали ----------

    def _write(self, *parts):
        """parts: (текст, тег) или текст."""
        for part in parts:
            text, tag = part if isinstance(part, tuple) else (part, None)
            self.details.insert(tk.END, text, tag)

    def _kv(self, key, value, mono=False):
        self._write((f"{key}\t", "key"), (f"{value}\n", "mono" if mono else None))

    def show_details(self):
        self.details.configure(state=tk.NORMAL)
        self.details.delete("1.0", tk.END)
        node = self._selected_node()
        if not node:
            self._write(("Выберите объект слева\n", "muted"),
                        ("\nДвойной щелчок — изменить, Delete — удалить, правая кнопка — меню.", "muted"))
        elif node[0] == "core":
            self._core_details(node[1])
        elif node[0] == "cluster":
            self._cluster_details(node[1])
        else:
            self._switch_details(node[1])
        self.details.configure(state=tk.DISABLED)

    def _core_details(self, core_id):
        core = db.get_core_switch(core_id)
        if not core:
            return
        tors = [sw for sw in db.list_switches() if sw["core_switch_id"] == core_id]
        self._write((f"{core['hostname']}\n", "h1"), ("CORE-КОММУТАТОР\n", "badge"))
        self._kv("IP", core["ip"] or "—", mono=True)
        self._kv("Подключено TOR", len(tors))
        if tors:
            self._write(("Подключения\n", "section"))
            for sw in tors:
                self._write((f"{sw['core_interface']}\t", "mono"), f"→ {sw['hostname']}  ",
                            (f"{sw['cluster_name']}\n", "muted"))

    def _cluster_details(self, cluster_id):
        cl = db.get_cluster(cluster_id)
        if not cl:
            return
        tors = db.list_switches(cluster_id)
        self._write((f"{cl['name']}\n", "h1"), ("КЛАСТЕР\n", "badge"))
        self._kv("TOR-коммутаторов", len(tors))
        for sw in tors:
            ifaces = db.get_switch_interfaces(sw["id"])
            self._write((f"{sw['hostname']}\n", "section"))
            self._kv("IP", sw["ip"], mono=True)
            self._kv("Тип", self.TYPE_LABELS.get(sw["type"], sw["type"]))
            self._kv("Uplink", f"{sw['uplink_interface']} → {sw['core_hostname']} {sw['core_interface']}", mono=True)
            self._kv("Серверных порт.", len(ifaces))

    def _switch_details(self, switch_id):
        sw = db.get_switch(switch_id)
        if not sw:
            return
        ifaces = db.get_switch_interfaces(switch_id)
        self._write((f"{sw['hostname']}\n", "h1"),
                    (f"TOR-КОММУТАТОР · {self.TYPE_LABELS.get(sw['type'], sw['type']).upper()}\n", "badge"))
        self._kv("IP", sw["ip"], mono=True)
        self._kv("Кластер", sw["cluster_name"])
        self._kv("Uplink", sw["uplink_interface"], mono=True)
        self._kv("Core", sw["core_hostname"])
        self._kv("Интерфейс на Core", sw["core_interface"], mono=True)
        self._write((f"Интерфейсы серверов ({len(ifaces)})\n", "section"))
        if ifaces:
            self._write((", ".join(ifaces) + "\n", "mono"))
        else:
            self._write(("нет\n", "muted"))

    # ---------- Контекстное меню ----------

    def _context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.node_data:
            return
        self.tree.selection_set(iid)
        kind, obj_id = self.node_data[iid]
        self.menu.delete(0, tk.END)
        self.menu.add_command(label="Изменить", command=self.edit_selected)
        if kind == "cluster":
            self.menu.add_command(label="Добавить TOR в кластер",
                                  command=lambda: self.add_switch(cluster_id=obj_id))
        elif kind == "core":
            self.menu.add_command(label="Добавить TOR к этому Core",
                                  command=lambda: self.add_switch(core_id=obj_id))
        elif kind == "switch":
            self.menu.add_command(label="Дублировать", command=lambda: self.add_switch(template_id=obj_id))
        self.menu.add_separator()
        self.menu.add_command(label="Удалить", command=self.delete_selected)
        self.menu.tk_popup(event.x_root, event.y_root)

    # ---------- Действия ----------

    def add_cluster(self):
        r = dialogs.ask_cluster(self)
        if not r:
            return
        if db.add_cluster(r["name"]):
            self.app.set_status(f"Кластер «{r['name']}» добавлен")
            self.refresh()
        else:
            messagebox.showerror("Ошибка", f"Кластер «{r['name']}» уже существует.", parent=self)

    def add_core(self):
        r = dialogs.ask_core(self)
        if not r:
            return
        if db.add_core_switch(r["hostname"], r["ip"]):
            self.app.set_status(f"Core «{r['hostname']}» добавлен")
            self.refresh()
        else:
            messagebox.showerror("Ошибка", f"Core «{r['hostname']}» уже существует.", parent=self)

    def add_switch(self, cluster_id=None, core_id=None, template_id=None):
        clusters, cores = db.list_clusters(), db.list_core_switches()
        if not clusters:
            messagebox.showwarning("Нет кластеров", "Сначала создайте кластер.", parent=self)
            return
        if not cores:
            messagebox.showwarning("Нет Core", "Сначала добавьте Core-коммутатор.", parent=self)
            return

        initial = {}
        node = self._selected_node()
        if template_id:
            initial = db.get_switch(template_id)
            initial["interfaces"] = ", ".join(db.get_switch_interfaces(template_id))
            initial.update(id=None, hostname="", ip="")
        elif node and node[0] == "switch":
            sw = db.get_switch(node[1])
            initial = {"cluster_id": sw["cluster_id"], "core_switch_id": sw["core_switch_id"], "type": sw["type"]}
        elif node and node[0] == "cluster":
            initial = {"cluster_id": node[1]}
        elif node and node[0] == "core":
            initial = {"core_switch_id": node[1]}
        if cluster_id:
            initial["cluster_id"] = cluster_id
        if core_id:
            initial["core_switch_id"] = core_id

        r = dialogs.ask_switch(self, clusters, cores, initial)
        if not r:
            return
        sid = db.add_switch(r["cluster_id"], r["hostname"], r["ip"], r["type"],
                            r["uplink_interface"], r["core_switch_id"], r["core_interface"])
        if sid:
            db.set_switch_interfaces(sid, r["interfaces"])
            self.app.set_status(f"TOR {r['hostname']} добавлен")
            self.refresh()
        else:
            messagebox.showerror("Ошибка", f"Коммутатор с IP {r['ip']} уже существует.", parent=self)

    def edit_selected(self):
        node = self._selected_node()
        if not node:
            return
        kind, obj_id = node
        if kind == "core":
            core = db.get_core_switch(obj_id)
            r = dialogs.ask_core(self, core)
            if r and not db.update_core_switch(obj_id, r["hostname"], r["ip"]):
                messagebox.showerror("Ошибка", "Core с таким hostname уже существует.", parent=self)
                return
        elif kind == "cluster":
            r = dialogs.ask_cluster(self, db.get_cluster(obj_id))
            if r and not db.update_cluster(obj_id, r["name"]):
                messagebox.showerror("Ошибка", "Кластер с таким именем уже существует.", parent=self)
                return
        else:
            sw = db.get_switch(obj_id)
            sw["interfaces"] = ", ".join(db.get_switch_interfaces(obj_id))
            r = dialogs.ask_switch(self, db.list_clusters(), db.list_core_switches(), sw)
            if r:
                if not db.update_switch(obj_id, r["cluster_id"], r["hostname"], r["ip"], r["type"],
                                        r["uplink_interface"], r["core_switch_id"], r["core_interface"]):
                    messagebox.showerror("Ошибка", "Коммутатор с таким IP уже существует.", parent=self)
                    return
                db.set_switch_interfaces(obj_id, r["interfaces"])
        if r:
            self.app.set_status("Изменения сохранены")
            self.refresh()

    def delete_selected(self):
        node = self._selected_node()
        if not node:
            return
        kind, obj_id = node
        if kind == "core":
            core = db.get_core_switch(obj_id)
            if not messagebox.askyesno("Удаление", f"Удалить Core {core['hostname']}?", parent=self):
                return
            if not db.delete_core_switch(obj_id):
                messagebox.showwarning("Нельзя удалить",
                                       f"К {core['hostname']} привязаны TOR-коммутаторы. "
                                       "Сначала переназначьте или удалите их.", parent=self)
                return
        elif kind == "cluster":
            cl = db.get_cluster(obj_id)
            n = len(db.list_switches(obj_id))
            extra = f" и {n} TOR-коммутатор(ов) в нём" if n else ""
            if not messagebox.askyesno("Удаление", f"Удалить кластер «{cl['name']}»{extra}?", parent=self):
                return
            db.delete_cluster(obj_id)
        else:
            sw = db.get_switch(obj_id)
            if not messagebox.askyesno("Удаление", f"Удалить TOR {sw['hostname']} ({sw['ip']})?", parent=self):
                return
            db.delete_switch(obj_id)
        self.app.set_status("Удалено")
        self.refresh()


# ======================================================================
#  VLAN
# ======================================================================

class VlanPage(Page):
    title = "VLAN"
    subtitle = "Общая база VLAN для генерации конфигов"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.action("+ VLAN", self.add, "Accent.TButton")

        outer, inner = card(self.body, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(inner, style="Card.TFrame")
        top.pack(fill=tk.X, pady=(0, 10))
        self.search = PlaceholderEntry(top, "Фильтр по номеру или описанию…")
        self.search.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search.var.trace_add("write", lambda *_: self.refresh())
        ttk.Button(top, text="Удалить", style="Danger.TButton", command=self.delete).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(top, text="Изменить", command=self.edit).pack(side=tk.RIGHT, padx=(8, 0))

        frame, self.tree = scrolled(inner, lambda p: ttk.Treeview(
            p, columns=("vlan", "desc"), show="headings", selectmode="extended"))
        frame.pack(fill=tk.BOTH, expand=True)
        self.tree.heading("vlan", text="VLAN ID", anchor=tk.W)
        self.tree.heading("desc", text="Описание", anchor=tk.W)
        self.tree.column("vlan", width=110, stretch=False)
        self.tree.column("desc", width=500)
        self.tree.tag_configure("odd", background=theme.SURFACE_ALT)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<Delete>", lambda e: self.delete())

    def on_show(self):
        self.refresh()

    def refresh(self):
        query = self.search.value().lower()
        self.tree.delete(*self.tree.get_children())
        vlans = db.list_vlans()
        shown = [v for v in vlans if not query or query in str(v["vlan_id"]) or query in (v["description"] or "").lower()]
        for i, v in enumerate(shown):
            self.tree.insert("", tk.END, iid=str(v["vlan_id"]), values=(v["vlan_id"], v["description"] or ""),
                             tags=("odd",) if i % 2 else ())
        self.app.set_status(f"VLAN в базе: {len(vlans)}")

    def add(self):
        r = dialogs.ask_vlan(self)
        if not r:
            return
        if db.add_vlan(r["vlan_id"], r["description"]):
            self.refresh()
            self.app.set_status(f"VLAN {r['vlan_id']} добавлен")
        else:
            messagebox.showerror("Ошибка", f"VLAN {r['vlan_id']} уже есть в базе.", parent=self)

    def edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        vlan = db.get_vlan_by_id(int(sel[0]))
        r = dialogs.ask_vlan(self, vlan)
        if r:
            db.update_vlan(r["vlan_id"], r["description"])
            self.refresh()

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        names = ", ".join(sel) if len(sel) <= 5 else f"{len(sel)} шт."
        if messagebox.askyesno("Удаление", f"Удалить VLAN: {names}?", parent=self):
            for vlan_id in sel:
                db.delete_vlan(int(vlan_id))
            self.refresh()


# ======================================================================
#  Генератор конфигов
# ======================================================================

class GeneratorPage(Page):
    title = "Генератор конфигов"
    subtitle = "Отметьте кластеры и VLAN — предпросмотр обновляется сразу"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.configs = {}
        self.action("Сохранить…", self.save_file, "Accent.TButton")
        self.action("По файлу на коммутатор…", self.save_dir)
        self.action("Копировать", self.copy)

        paned = ttk.PanedWindow(self.body, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, width=340)
        paned.add(left, weight=0)
        c1_outer, c1 = card(left, padding=12)
        c1_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.clusters = CheckList(c1, "Кластеры", on_change=self.regenerate)
        self.clusters.pack(fill=tk.BOTH, expand=True)
        c2_outer, c2 = card(left, padding=12)
        c2_outer.pack(fill=tk.BOTH, expand=True)
        self.vlans = CheckList(c2, "VLAN", on_change=self.regenerate)
        self.vlans.pack(fill=tk.BOTH, expand=True)

        right_outer, right = card(paned, padding=4)
        paned.add(right_outer, weight=3)
        head = ttk.Frame(right, style="Card.TFrame", padding=(12, 8, 12, 0))
        head.pack(fill=tk.X)
        ttk.Label(head, text="Предпросмотр", style="CardTitle.TLabel").pack(side=tk.LEFT)
        self.summary = ttk.Label(head, style="CardMuted.TLabel")
        self.summary.pack(side=tk.LEFT, padx=10)

        frame, self.preview = scrolled(right, lambda p: tk.Text(p, width=60), horizontal=True)
        frame.pack(fill=tk.BOTH, expand=True)
        theme.style_text(self.preview)
        p = self.preview
        p.tag_configure("banner", foreground=theme.ACCENT, font=("Consolas", 10, "bold"))
        p.tag_configure("comment", foreground=theme.SUCCESS)
        p.tag_configure("keyword", foreground=theme.ACCENT)
        p.tag_configure("quit", foreground=theme.MUTED)
        p.tag_configure("muted", foreground=theme.MUTED, font=theme.FONT)

    def on_show(self):
        self.clusters.set_items([(c["id"], f"{c['name']}  ·  {c['switch_count']} TOR") for c in db.list_clusters()])
        self.vlans.set_items([(v["vlan_id"], f"{v['vlan_id']:<6} {v['description'] or ''}") for v in db.list_vlans()])
        self.regenerate()

    def regenerate(self):
        cluster_ids, vlan_ids = self.clusters.selected(), self.vlans.selected()
        self.configs = config_generator.generate_configs_for_selection(cluster_ids, vlan_ids) \
            if cluster_ids and vlan_ids else {}

        p = self.preview
        p.configure(state=tk.NORMAL)
        p.delete("1.0", tk.END)
        if not self.configs:
            hint = "Отметьте хотя бы один кластер и один VLAN слева."
            if not self.clusters.labels:
                hint = "Нет кластеров — добавьте их на вкладке «Сеть»."
            elif not self.vlans.labels:
                hint = "База VLAN пуста — добавьте VLAN на вкладке «VLAN»."
            p.insert(tk.END, hint, "muted")
            self.summary.configure(text="")
        else:
            text = config_generator.format_configs(self.configs)
            for line in text.split("\n"):
                s = line.strip()
                if s.startswith("=") or s.startswith("Коммутатор:"):
                    tag = "banner"
                elif s.startswith("!"):
                    tag = "comment"
                elif s == "quit":
                    tag = "quit"
                elif s.startswith(("vlan ", "interface ")):
                    tag = "keyword"
                else:
                    tag = None
                p.insert(tk.END, line + "\n", tag)
            lines = sum(len(c) for c in self.configs.values())
            self.summary.configure(text=f"{len(self.configs)} коммутатор(ов) · {lines} строк")
        p.configure(state=tk.DISABLED)
        self.app.set_status(f"Выбрано кластеров: {len(cluster_ids)}, VLAN: {len(vlan_ids)}")

    def _require(self):
        if not self.configs:
            messagebox.showinfo("Нечего сохранять", "Отметьте кластеры и VLAN.", parent=self)
            return False
        return True

    def copy(self):
        if self._require():
            self.clipboard_clear()
            self.clipboard_append(config_generator.format_configs(self.configs))
            self.app.set_status("Конфиги скопированы в буфер обмена")

    def save_file(self):
        if not self._require():
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt", initialfile="huawei_configs.txt",
                                            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            config_generator.save_configs_to_file(self.configs, path)
            self.app.set_status(f"Сохранено: {path}")

    def save_dir(self):
        if not self._require():
            return
        path = filedialog.askdirectory(parent=self, title="Папка для конфигов (по файлу на коммутатор)")
        if path:
            n = config_generator.save_configs_to_dir(self.configs, path)
            self.app.set_status(f"Сохранено файлов: {n} → {path}")


# ======================================================================
#  Парсер USG
# ======================================================================

class UsgPage(Page):
    title = "Парсер USG"
    subtitle = "Поиск security-policy и nat-policy по IP или подсети"

    ALL_ZONES = "Все зоны"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.parsed = None
        self.parsed_key = None      # (путь, mtime) — перечитываем, только если файл изменился
        self.rows = []
        self.sort_state = (None, False)

        self.action("Экспорт в Excel…", self.save_excel)

        # --- Форма ---
        form_outer, form = card(self.body, padding=16)
        form_outer.pack(fill=tk.X, pady=(0, 12))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Конфиг", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.file_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.file_var, state="readonly").grid(row=0, column=1, columnspan=4, sticky="ew")
        ttk.Button(form, text="Открыть…", command=self.browse).grid(row=0, column=5, sticky="ew", padx=(8, 0))
        self.file_info = ttk.Label(form, text="Файл не выбран", style="CardMuted.TLabel")
        self.file_info.grid(row=1, column=1, columnspan=5, sticky="w", pady=(4, 12))

        ttk.Label(form, text="IP / подсеть", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.ip_entry = PlaceholderEntry(form, "10.0.0.5 или 10.0.0.0/24", width=30)
        self.ip_entry.grid(row=2, column=1, sticky="ew")
        self.ip_entry.bind("<Return>", lambda e: self.run_search())

        self.zone = ttk.Combobox(form, state="readonly", width=18, values=[self.ALL_ZONES])
        self.zone.current(0)
        self.zone.grid(row=2, column=2, padx=(8, 0))

        seg = ttk.Frame(form, style="Card.TFrame")
        seg.grid(row=2, column=3, padx=(12, 0))
        self.side = tk.StringVar(value="both")
        for value, text in (("both", "SRC и DST"), ("src", "SRC"), ("dst", "DST")):
            ttk.Radiobutton(seg, text=text, value=value, variable=self.side, style="Segment.Toolbutton",
                            command=self.run_search_if_ready).pack(side=tk.LEFT)

        self.include_any = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="учитывать any", variable=self.include_any,
                        command=self.run_search_if_ready).grid(row=2, column=4, padx=(12, 0))
        ttk.Button(form, text="Найти", style="Accent.TButton", command=self.run_search).grid(
            row=2, column=5, sticky="ew", padx=(8, 0))
        self.zone.bind("<<ComboboxSelected>>", lambda e: self.run_search_if_ready())

        # --- Результаты + детали правила ---
        paned = ttk.PanedWindow(self.body, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        res_outer, res = card(paned, padding=12)
        paned.add(res_outer, weight=4)
        head = ttk.Frame(res, style="Card.TFrame")
        head.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(head, text="Результат", style="CardTitle.TLabel").pack(side=tk.LEFT)
        self.count = ttk.Label(head, style="CardMuted.TLabel")
        self.count.pack(side=tk.LEFT, padx=10)
        self.filter = PlaceholderEntry(head, "Фильтр по результату…", width=32)
        self.filter.pack(side=tk.RIGHT)
        self.filter.var.trace_add("write", lambda *_: self.fill_table())

        keys = [k for k, _, _ in usg_parser.COLUMNS]
        frame, self.table = scrolled(res, lambda p: ttk.Treeview(p, columns=keys, show="headings"), horizontal=True)
        frame.pack(fill=tk.BOTH, expand=True)
        for key, title, width in usg_parser.COLUMNS:
            self.table.heading(key, text=title, anchor=tk.W, command=lambda k=key: self.sort_by(k))
            self.table.column(key, width=width, minwidth=60, stretch=False)
        self.table.tag_configure("odd", background=theme.SURFACE_ALT)
        self.table.tag_configure("deny", foreground=theme.DANGER)
        self.table.tag_configure("nat", foreground=theme.ACCENT)
        self.table.bind("<<TreeviewSelect>>", lambda e: self.show_rule())
        self.table.bind("<Control-c>", self.copy_rows)
        self.table.bind("<Control-C>", self.copy_rows)

        det_outer, det = card(paned, padding=4)
        paned.add(det_outer, weight=1)
        frame, self.rule_text = scrolled(det, lambda p: tk.Text(p, height=8), horizontal=True)
        frame.pack(fill=tk.BOTH, expand=True)
        theme.style_text(self.rule_text)
        self.rule_text.tag_configure("muted", foreground=theme.MUTED, font=theme.FONT)
        self.rule_text.tag_configure("head", foreground=theme.ACCENT)
        self._set_rule_text([("Выберите строку, чтобы увидеть правило целиком. Ctrl+C — копировать строки.", "muted")])

        last = load_settings().get("usg_file")
        if last and os.path.exists(last):
            self.load_file(last)

    def on_show(self):
        self.app.set_status(f"Найдено строк: {len(self.rows)}" if self.rows else "")

    # ---------- Файл ----------

    def browse(self):
        path = filedialog.askopenfilename(parent=self, title="Конфигурация USG",
                                          filetypes=[("Text files", "*.txt *.cfg *.zip"), ("All files", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            self.parsed = usg_parser.parse_config(text)
            self.parsed_key = (path, os.path.getmtime(path))
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}", parent=self)
            return False
        self.file_var.set(path)
        p = self.parsed
        self.file_info.configure(text=(
            f"security-policy: {len(p['security_rules'])}  ·  nat-policy: {len(p['nat_rules'])}  ·  "
            f"address-set: {len(p['address_sets'])}  ·  service-set: {len(p['service_sets'])}  ·  "
            f"зон: {len(p['zones'])}"))
        current = self.zone.get()
        self.zone.configure(values=[self.ALL_ZONES] + p["zones"])
        if current not in p["zones"]:
            self.zone.current(0)
        settings = load_settings()
        settings["usg_file"] = path
        save_settings(settings)
        return True

    def _ensure_fresh(self):
        """Перепарсит конфиг, если файл изменился с момента загрузки."""
        if not self.parsed_key:
            return False
        path, mtime = self.parsed_key
        try:
            if os.path.getmtime(path) != mtime:
                return self.load_file(path)
        except OSError:
            pass
        return True

    # ---------- Поиск ----------

    def run_search_if_ready(self):
        if self.parsed and self.ip_entry.value():
            self.run_search()

    def run_search(self):
        if not self._ensure_fresh():
            messagebox.showwarning("Нет конфига", "Сначала откройте файл конфигурации USG.", parent=self)
            return
        target = self.ip_entry.value()
        if not target:
            self.ip_entry.focus_set()
            return
        try:
            usg_parser.parse_target(target)
        except ValueError:
            messagebox.showerror("Неверный адрес", f"«{target}» — не IPv4-адрес или подсеть.", parent=self)
            return
        zone = self.zone.get()
        self.rows = usg_parser.search(self.parsed, target, None if zone == self.ALL_ZONES else zone,
                                      self.side.get(), self.include_any.get())
        self.sort_state = (None, False)
        self.fill_table()
        rules = len({id(r["rule"]) for r in self.rows})
        self.app.set_status(f"{target}: правил {rules}, строк {len(self.rows)}")

    def _visible(self):
        """[(индекс в self.rows, строка)] с учётом фильтра."""
        query = self.filter.value().lower()
        return [(i, r) for i, r in enumerate(self.rows)
                if not query or any(query in str(v).lower() for v in usg_parser.row_values(r))]

    def _visible_rows(self):
        return [r for _, r in self._visible()]

    def fill_table(self):
        self.table.delete(*self.table.get_children())
        visible = self._visible()
        for n, (idx, row) in enumerate(visible):
            tags = ["odd"] if n % 2 else []
            if row["action"] == "deny":
                tags.append("deny")
            elif row["kind"] == "nat-policy":
                tags.append("nat")
            self.table.insert("", tk.END, iid=str(idx), values=usg_parser.row_values(row), tags=tags)
        total = len(self.rows)
        self.count.configure(text=f"{len(visible)} из {total}" if len(visible) != total else f"{total} строк")

    def sort_by(self, key):
        prev_key, desc = self.sort_state
        desc = not desc if prev_key == key else False
        self.sort_state = (key, desc)
        self.rows.sort(key=lambda r: str(r[key]).lower(), reverse=desc)
        for k, title, _ in usg_parser.COLUMNS:
            arrow = (" ▼" if desc else " ▲") if k == key else ""
            self.table.heading(k, text=title + arrow)
        self.fill_table()

    def _set_rule_text(self, parts):
        t = self.rule_text
        t.configure(state=tk.NORMAL)
        t.delete("1.0", tk.END)
        for text, tag in parts:
            t.insert(tk.END, text, tag)
        t.configure(state=tk.DISABLED)

    def show_rule(self):
        sel = self.table.selection()
        if not sel:
            return
        rule = self.rows[int(sel[0])]["rule"]
        parts = []
        for i, line in enumerate(rule["raw"]):
            parts.append((line + "\n", "head" if i == 0 else None))
        self._set_rule_text(parts)

    def copy_rows(self, _=None):
        sel = self.table.selection()
        if not sel:
            return
        lines = ["\t".join(str(v) for v in usg_parser.row_values(self.rows[int(i)])) for i in sel]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.app.set_status(f"Скопировано строк: {len(lines)}")

    def save_excel(self):
        rows = self._visible_rows()
        if not rows:
            messagebox.showinfo("Нечего сохранять", "Сначала выполните поиск.", parent=self)
            return
        name = "usg_" + self.ip_entry.value().replace("/", "_") + ".xlsx"
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", initialfile=name,
                                            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if not path:
            return
        try:
            excel_export.save_usg_rows(rows, path)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл (открыт в Excel?):\n{e}", parent=self)
            return
        self.app.set_status(f"Excel сохранён: {path}")


# ======================================================================
#  Главное окно
# ======================================================================

class HuaweiConfigApp:
    PAGES = [
        ("network", "Сеть", NetworkPage),
        ("vlan", "VLAN", VlanPage),
        ("generator", "Генератор", GeneratorPage),
        ("usg", "Парсер USG", UsgPage),
    ]

    def __init__(self, root):
        self.root = root
        root.title("Huawei Config Tool")
        root.geometry("1360x840")
        root.minsize(1100, 640)
        theme.apply(root)

        self._build_sidebar()

        main = ttk.Frame(root)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.status = ttk.Label(main, style="Status.TLabel", padding=(28, 0, 28, 10))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self.container = ttk.Frame(main)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.pages = {}
        for key, _, cls in self.PAGES:
            self.pages[key] = cls(self.container, self)
        self.current = None
        self.show(load_settings().get("page", "network"))

        for i, (key, _, _) in enumerate(self.PAGES, 1):
            root.bind(f"<Control-Key-{i}>", lambda e, k=key: self.show(k))

    def _build_sidebar(self):
        side = tk.Frame(self.root, bg=theme.SIDEBAR, width=210)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)

        tk.Label(side, text="Huawei", bg=theme.SIDEBAR, fg="#FFFFFF",
                 font=("Segoe UI Semibold", 15), anchor="w").pack(fill=tk.X, padx=22, pady=(24, 0))
        tk.Label(side, text="Config Tool", bg=theme.SIDEBAR, fg=theme.SIDEBAR_TEXT,
                 font=theme.FONT_SMALL, anchor="w").pack(fill=tk.X, padx=22, pady=(0, 24))

        self.nav = {}
        for i, (key, label, _) in enumerate(self.PAGES, 1):
            row = tk.Frame(side, bg=theme.SIDEBAR, cursor="hand2")
            row.pack(fill=tk.X, pady=1)
            bar = tk.Frame(row, bg=theme.SIDEBAR, width=3)
            bar.pack(side=tk.LEFT, fill=tk.Y)
            text = tk.Label(row, text=label, bg=theme.SIDEBAR, fg=theme.SIDEBAR_TEXT,
                            font=theme.FONT, anchor="w", padx=19, pady=9)
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            hint = tk.Label(row, text=f"Ctrl+{i}", bg=theme.SIDEBAR, fg="#5A6378", font=theme.FONT_SMALL, padx=14)
            hint.pack(side=tk.RIGHT)
            for w in (row, text, hint):
                w.bind("<Button-1>", lambda e, k=key: self.show(k))
                w.bind("<Enter>", lambda e, k=key: self._hover(k, True))
                w.bind("<Leave>", lambda e, k=key: self._hover(k, False))
            self.nav[key] = (row, bar, text, hint)

        bottom = tk.Frame(side, bg=theme.SIDEBAR)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=18)
        export = tk.Label(bottom, text="Экспорт базы в JSON", bg=theme.SIDEBAR_HOVER, fg=theme.SIDEBAR_TEXT,
                          font=theme.FONT_SMALL, pady=7, cursor="hand2")
        export.pack(fill=tk.X)
        export.bind("<Button-1>", lambda e: self.export_json())
        export.bind("<Enter>", lambda e: export.configure(fg="#FFFFFF"))
        export.bind("<Leave>", lambda e: export.configure(fg=theme.SIDEBAR_TEXT))
        tk.Label(bottom, text=os.path.basename(db.DB_FILE), bg=theme.SIDEBAR, fg="#5A6378",
                 font=theme.FONT_SMALL, anchor="w").pack(fill=tk.X, pady=(8, 0))

    def _paint_nav(self, key, state):
        row, bar, text, hint = self.nav[key]
        bg = {"active": theme.SIDEBAR_ACTIVE, "hover": theme.SIDEBAR_HOVER}.get(state, theme.SIDEBAR)
        for w in (row, text, hint):
            w.configure(bg=bg)
        bar.configure(bg=theme.ACCENT if state == "active" else bg)
        text.configure(fg="#FFFFFF" if state in ("active", "hover") else theme.SIDEBAR_TEXT,
                       font=theme.FONT_BOLD if state == "active" else theme.FONT)

    def _hover(self, key, entering):
        if key != self.current:
            self._paint_nav(key, "hover" if entering else "idle")

    def show(self, key):
        if key not in self.pages:
            key = "network"
        if self.current:
            self.pages[self.current].pack_forget()
            self._paint_nav(self.current, "idle")
        self.current = key
        self._paint_nav(key, "active")
        self.pages[key].pack(fill=tk.BOTH, expand=True)
        self.pages[key].on_show()
        settings = load_settings()
        settings["page"] = key
        save_settings(settings)

    def set_status(self, text):
        self.status.configure(text=text)

    def export_json(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                                            initialfile="switches_export.json",
                                            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if path:
            count = db.export_to_json(path)
            self.set_status(f"Экспортировано кластеров: {count} → {path}")


def main():
    theme.enable_dpi_awareness()
    db.init_db()
    root = tk.Tk()
    HuaweiConfigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
