"""Browser-free desktop dashboard. Uses only Python's standard library and Tk.

HTTP runs in one worker; all widgets are updated on the Tk main thread. Metrics
continue to be collected by the existing service when this window is closed.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import threading
from contextlib import suppress
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

sys.dont_write_bytecode = True

ENDPOINTS = {
    "health": "health",
    "system": "system",
    "current": "metrics/current",
    "history": "metrics/history?minutes=30",
    "processes": "processes?limit=8",
    "services": "services",
    "alerts": "alerts?minutes=1440",
}
BG, PANEL, FG, MUTED = "#0b0e11", "#12171d", "#e2e8f0", "#94a3b8"
ACCENT, GREEN, RED, AMBER = "#4fd1c5", "#42c665", "#ff554b", "#ffbf47"


def format_bytes(value):
    if value is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def rate(value):
    return "—" if value is None else format_bytes(value) + "/s"


def percent(value):
    return "—" if value is None else f"{value:.1f}%"


def clock(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")


def chart_segments(points, key, width, height, maximum):
    """Preserve missing-rate gaps and place irregular samples by their timestamp."""
    if not points:
        return []
    times = [
        datetime.fromisoformat(p["collected_at"].replace("Z", "+00:00")).timestamp() for p in points
    ]
    span = max(times[-1] - times[0], 1)
    segments, segment = [], []
    for point, timestamp in zip(points, times, strict=True):
        value = point.get(key)
        if value is None or not math.isfinite(value):
            if segment:
                segments.append(segment)
            segment = []
            continue
        segment.extend(
            (
                52 + (timestamp - times[0]) / span * width,
                12 + height * (1 - max(0, min(value / maximum, 1))),
            )
        )
    if segment:
        segments.append(segment)
    return segments


def collect(url, opener, cancelled=lambda: False):
    data, errors = {}, {}
    for name, endpoint in ENDPOINTS.items():
        if cancelled():
            break
        try:
            with opener.open(url.rstrip("/") + "/api/" + endpoint, timeout=2) as response:
                data[name] = json.load(response)
        except (HTTPError, URLError, OSError, ValueError) as error:
            errors[name] = str(error)
    return data, errors


class Poller:
    def __init__(self, url, interval=10):
        self.url, self.interval = url, interval
        self.results = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.enabled = threading.Event()
        self.enabled.set()
        self.wake = threading.Event()
        self.generation = 0
        self.thread = threading.Thread(target=self.run, daemon=True)

    def set_visible(self, visible):
        self.generation += 1
        if visible:
            self.enabled.set()
        else:
            self.enabled.clear()
        self.wake.set()

    def stop(self):
        self.stopped.set()
        self.wake.set()

    def run(self):
        opener = build_opener(ProxyHandler({}))
        while not self.stopped.is_set():
            self.wake.clear()
            if self.enabled.is_set():
                generation = self.generation
                result = collect(
                    self.url,
                    opener,
                    lambda generation=generation: (
                        self.stopped.is_set()
                        or not self.enabled.is_set()
                        or generation != self.generation
                    ),
                )
                if (
                    self.enabled.is_set()
                    and not self.stopped.is_set()
                    and generation == self.generation
                ):
                    with suppress(queue.Empty):
                        self.results.get_nowait()
                    self.results.put_nowait(result)
            self.wake.wait(self.interval)


class Dashboard:
    def __init__(self, root, url):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk, self.root = tk, ttk, root
        self.data, self.tables, self.table_values, self.charts = {}, {}, {}, []
        self.sort = tk.StringVar(value="top_by_cpu")
        self.poller = Poller(url)
        root.title("Linux Server Monitor")
        root.geometry("1120x850")
        root.minsize(850, 670)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=FG,
            rowheight=27,
            borderwidth=0,
            font=("DejaVu Sans", 10),
        )
        style.configure(
            "Treeview.Heading", background=PANEL, foreground=MUTED, font=("DejaVu Sans", 10)
        )
        style.map("Treeview", background=[("selected", "#23434b")])
        style.configure("TScrollbar", background="#24303b", troughcolor=PANEL)

        header = tk.Frame(root, bg=PANEL, padx=18, pady=12)
        header.pack(fill="x")
        self.identity = self.label(header, "Linux Server Monitor", size=15, bold=True)
        self.identity.pack(anchor="w")
        self.system = self.label(header, "Connecting to the monitoring service…", color=MUTED)
        self.system.pack(anchor="w", pady=(5, 0))
        self.status = self.label(root, "Waiting for first reading…", color=MUTED)
        self.status.pack(anchor="w", padx=18, pady=8)
        viewport = tk.Frame(root, bg=BG)
        viewport.pack(fill="both", expand=True)
        scroll = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=scroll.yview)
        scrollbar.pack(side="right", fill="y")
        scroll.pack(side="left", fill="both", expand=True)
        scroll.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(scroll, bg=BG, padx=16)
        window = scroll.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: scroll.configure(scrollregion=scroll.bbox("all")))
        scroll.bind("<Configure>", lambda event: scroll.itemconfigure(window, width=event.width))
        root.bind("<Button-4>", lambda event: scroll.yview_scroll(-1, "units"))
        root.bind("<Button-5>", lambda event: scroll.yview_scroll(1, "units"))
        root.bind(
            "<MouseWheel>", lambda event: scroll.yview_scroll(-int(event.delta / 120), "units")
        )
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(3, weight=1)

        current = self.panel(body, "Current usage", 0, 0, colspan=3)
        self.stats = []
        for i, title in enumerate(("CPU", "Memory", "Swap", "Network ↑ / ↓")):
            current.columnconfigure(i, weight=1)
            card = tk.Frame(current, bg=PANEL, padx=10, pady=6)
            card.grid(row=1, column=i, sticky="nsew")
            self.label(card, title, color=MUTED).pack(anchor="w")
            value = self.label(card, "—", size=21, bold=True)
            value.pack(anchor="w", pady=5)
            detail = self.label(card, "", color=MUTED)
            detail.pack(anchor="w")
            self.stats.append((value, detail))

        disks = self.panel(body, "Disks", 1, 0, colspan=3)
        self.table(
            disks,
            "disks",
            ("Mount", "Device", "Used", "Total", "Usage"),
            3,
            widths=(270, 170, 120, 120, 100),
        )
        for col, (title, keys, colors, fixed) in enumerate(
            (
                ("CPU · last 30 min", ("cpu_percent",), (ACCENT,), 100),
                ("Memory · last 30 min", ("ram_percent",), ("#a78bfa",), 100),
                (
                    "Network · sent / received",
                    ("send_rate_bytes_per_sec", "recv_rate_bytes_per_sec"),
                    (ACCENT, "#a5d6ff"),
                    None,
                ),
            )
        ):
            panel = self.panel(body, title, 2, col)
            canvas = tk.Canvas(panel, bg=PANEL, height=145, highlightthickness=0)
            canvas.grid(row=1, column=0, sticky="ew")
            chart = (canvas, keys, colors, fixed)
            self.charts.append(chart)
            canvas.bind("<Configure>", lambda event, chart=chart: self.draw_chart(chart))

        processes = self.panel(body, "Top processes", 3, 0, colspan=2)
        processes.rowconfigure(2, weight=1)
        tabs = tk.Frame(processes, bg=PANEL)
        tabs.grid(row=1, column=0, sticky="w", pady=5)
        for text, value in (("By CPU", "top_by_cpu"), ("By memory", "top_by_memory")):
            tk.Radiobutton(
                tabs,
                text=text,
                value=value,
                variable=self.sort,
                command=self.draw_processes,
                bg=PANEL,
                fg=FG,
                selectcolor=PANEL,
                activebackground=PANEL,
                activeforeground=ACCENT,
            ).pack(side="left")
        self.table(
            processes,
            "processes",
            ("PID", "Process / user", "CPU", "Memory", "RSS"),
            8,
            row=2,
            widths=(70, 220, 70, 80, 100),
        )
        side = tk.Frame(body, bg=BG)
        side.grid(row=3, column=2, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(1, weight=1)
        services = self.panel(side, "Services", 0, 0)
        self.table(services, "services", ("Service", "State"), 3, widths=(130, 120))
        alerts = self.panel(side, "Alerts", 1, 0)
        alerts.rowconfigure(1, weight=1)
        self.table(alerts, "alerts", ("State", "Message"), 4, widths=(80, 170))
        self.alert_detail = self.label(alerts, "Select an alert to read its message", color=MUTED)
        self.alert_detail.configure(wraplength=280, justify="left")
        self.alert_detail.grid(row=2, column=0, sticky="ew", pady=4)
        self.tables["alerts"].bind("<<TreeviewSelect>>", self.show_alert)
        self.label(
            root,
            "Native desktop · refresh every 10s · backend keeps collecting when closed",
            color=MUTED,
        ).pack(anchor="w", padx=18, pady=8)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Map>", self.visibility)
        root.bind("<Unmap>", self.visibility)
        self.poller.thread.start()
        self.timer = root.after(100, self.drain)

    def label(self, parent, text, color=FG, size=10, bold=False):
        return self.tk.Label(
            parent,
            text=text,
            fg=color,
            bg=parent.cget("bg"),
            font=("DejaVu Sans", size, "bold" if bold else "normal"),
        )

    def panel(self, parent, title, row, col, colspan=1):
        panel = self.tk.Frame(parent, bg=PANEL, padx=10, pady=8)
        panel.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=4, pady=4)
        panel.columnconfigure(0, weight=1)
        self.label(panel, title, bold=True).grid(row=0, column=0, sticky="w", pady=(0, 4))
        return panel

    def table(self, parent, name, columns, height, row=1, widths=()):
        frame = self.tk.Frame(parent, bg=PANEL)
        frame.grid(row=row, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table = self.ttk.Treeview(frame, columns=columns, show="headings", height=height)
        for column, width in zip(columns, widths, strict=True):
            table.heading(column, text=column)
            table.column(column, width=width, minwidth=40, stretch=True)
        table.grid(row=0, column=0, sticky="nsew")
        scroll = self.ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        table.configure(yscrollcommand=scroll.set)
        for state, color in (
            ("CRITICAL", RED),
            ("WARNING", AMBER),
            ("RESOLVED", MUTED),
            ("RUNNING", GREEN),
            ("STOPPED", RED),
            ("UNKNOWN", MUTED),
        ):
            table.tag_configure(state, foreground=color)
        self.tables[name] = table

    def rows(self, name, rows):
        # Keep selections/scroll position and avoid repainting unchanged tables.
        if self.table_values.get(name) == rows:
            return
        table = self.tables[name]
        selected, view = table.selection(), table.yview()
        old = set(table.get_children())
        for index, (values, tag) in enumerate(rows):
            key = str(index)
            if key in old:
                table.item(key, values=values, tags=(tag,))
                old.remove(key)
            else:
                table.insert("", "end", iid=key, values=values, tags=(tag,))
        for key in old:
            table.delete(key)
        table.selection_set([key for key in selected if table.exists(key)])
        table.yview_moveto(view[0])
        self.table_values[name] = rows

    def draw_processes(self):
        processes = self.data.get("processes", {})
        self.rows(
            "processes",
            [
                (
                    (
                        p["pid"],
                        f"{p['name']} / {p.get('username') or '—'}",
                        percent(p["cpu_percent"]),
                        percent(p["memory_percent"]),
                        format_bytes(p["memory_rss_bytes"]),
                    ),
                    "",
                )
                for p in processes.get(self.sort.get(), [])
            ],
        )

    def show_alert(self, event=None):
        selection = self.tables["alerts"].selection()
        if selection:
            values = self.tables["alerts"].item(selection[0], "values")
            self.alert_detail.configure(text=values[1])

    def draw_chart(self, chart):
        canvas, keys, colors, fixed = chart
        points = self.data.get("history", {}).get("points", [])
        canvas.delete("all")
        width, height = max(canvas.winfo_width() - 65, 20), max(canvas.winfo_height() - 40, 20)
        maximum = fixed or max([1] + [p.get(key) or 0 for p in points for key in keys])
        for fraction in (0, 0.5, 1):
            y = 12 + height * (1 - fraction)
            canvas.create_line(52, y, 52 + width, y, fill="#27323e")
            text = percent(maximum * fraction) if fixed else rate(maximum * fraction)
            canvas.create_text(47, y, text=text, anchor="e", fill=MUTED, font=("DejaVu Sans", 8))
        if not points:
            canvas.create_text(
                52 + width / 2, 12 + height / 2, text="Waiting for history…", fill=MUTED
            )
            return
        for key, color in zip(keys, colors, strict=True):
            for segment in chart_segments(points, key, width, height, maximum):
                if len(segment) >= 4:
                    canvas.create_line(*segment, fill=color, width=1.5)
                elif segment:
                    x, y = segment
                    canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline="")
        for x, point, anchor in ((52, points[0], "w"), (52 + width, points[-1], "e")):
            canvas.create_text(
                x,
                26 + height,
                text=clock(point["collected_at"]),
                anchor=anchor,
                fill=MUTED,
                font=("DejaVu Sans", 8),
            )

    def render(self, data, errors):
        history_changed = data.get("history") != self.data.get("history")
        self.data.update(data)
        system, current = self.data.get("system"), self.data.get("current")
        if system:
            self.identity.configure(text=system["hostname"])
            self.system.configure(
                text=f"{system['os_name']} · {system['kernel']} · "
                f"{system['ip_address']} · uptime "
                f"{int(system['uptime_seconds'] // 3600)}h "
                f"{int(system['uptime_seconds'] % 3600 // 60)}m"
            )
        if current:
            cpu, memory, network = current["cpu"], current["memory"], current["network"]
            values = (
                (
                    percent(cpu["utilization_percent"]),
                    f"Load {cpu['load_avg_1m']:.2f} · {cpu['logical_cores']} cores",
                    "cpu",
                ),
                (
                    percent(memory["ram_percent"]),
                    f"{format_bytes(memory['ram_used_bytes'])} / "
                    f"{format_bytes(memory['ram_total_bytes'])}",
                    "memory",
                ),
                (percent(memory["swap_percent"]), format_bytes(memory["swap_used_bytes"]), "swap"),
                (
                    rate(network["send_rate_bytes_per_sec"]),
                    "↓ " + rate(network["recv_rate_bytes_per_sec"]),
                    "network",
                ),
            )
            alerts = self.data.get("alerts", {}).get("alerts", [])
            for (value, detail), (text, subtitle, key) in zip(self.stats, values, strict=True):
                state = next(
                    (
                        a["state"]
                        for a in alerts
                        if a["rule_key"] == key and a["state"] != "RESOLVED"
                    ),
                    None,
                )
                value.configure(text=text, fg={"CRITICAL": RED, "WARNING": AMBER}.get(state, FG))
                detail.configure(text=subtitle)
            self.rows(
                "disks",
                [
                    (
                        (
                            d["mountpoint"],
                            d["device"],
                            format_bytes(d["used_bytes"]),
                            format_bytes(d["total_bytes"]),
                            percent(d["percent"]),
                        ),
                        next(
                            (
                                a["state"]
                                for a in alerts
                                if a["rule_key"] == "disk"
                                and a["target"] == d["mountpoint"]
                                and a["state"] != "RESOLVED"
                            ),
                            "",
                        ),
                    )
                    for d in current["disks"]
                ],
            )
        self.draw_processes()
        self.rows(
            "services",
            [
                ((s["name"], s["state"].lower()), s["state"])
                for s in self.data.get("services", {}).get("services", [])
            ],
        )
        self.rows(
            "alerts",
            [
                ((a["state"].lower(), a["message"]), a["state"])
                for a in self.data.get("alerts", {}).get("alerts", [])
            ],
        )
        if self.tables["alerts"].get_children():
            self.show_alert()
        elif "alerts" in self.data:
            self.alert_detail.configure(text="No alerts · thresholds normal")
        if history_changed:
            for chart in self.charts:
                self.draw_chart(chart)
        if errors:
            self.status.configure(
                text="Update failed: "
                + ", ".join(errors)
                + " · previous readings retained · retrying automatically",
                fg=AMBER,
            )
        else:
            version = self.data.get("health", {}).get("version", "")
            self.status.configure(
                text=f"Connected · backend {version} · readings updated "
                + datetime.now().strftime("%H:%M:%S"),
                fg=GREEN,
            )

    def drain(self):
        try:
            data, errors = self.poller.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.render(data, errors)
        self.timer = self.root.after(500, self.drain)

    def visibility(self, event):
        if event.widget is self.root:
            self.poller.set_visible(self.root.state() not in ("iconic", "withdrawn"))

    def close(self):
        self.poller.stop()
        self.root.after_cancel(self.timer)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Native Linux Server Monitor")
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    args = parser.parse_args()
    try:
        import tkinter as tk
    except ImportError as error:
        print(
            f"Cannot open the native window: {error}. Use linux-monitor --browser.", file=sys.stderr
        )
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(
            f"Cannot open the native window: {error}. Use linux-monitor --browser.", file=sys.stderr
        )
        return 1
    Dashboard(root, args.url)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
