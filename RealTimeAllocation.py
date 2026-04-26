import random
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk


THEME = {
    "bg": "#0b1220",
    "panel": "#111b30",
    "panel_alt": "#16233f",
    "surface": "#dbeafe",
    "text": "#e5eefc",
    "muted": "#93a4c3",
    "accent": "#38bdf8",
    "accent_2": "#f59e0b",
    "success": "#34d399",
    "free": "#1e293b",
    "free_light": "#cbd5e1",
    "border": "#20304d",
}


PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def color_for(key: str) -> str:
    return PALETTE[sum(ord(ch) for ch in key) % len(PALETTE)]


@dataclass
class MemoryBlock:
    start: int
    size: int
    process_id: str | None = None
    label: str = "Free"

    @property
    def is_free(self) -> bool:
        return self.process_id is None


@dataclass
class FrameSlot:
    process_id: str | None = None
    page_number: int | None = None
    loaded_at: int = -1
    last_used: int = -1

    @property
    def is_free(self) -> bool:
        return self.process_id is None


class ContiguousMemorySimulator:
    def __init__(self, total_memory: int) -> None:
        self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, total_memory)]

    def reset(self, total_memory: int | None = None) -> None:
        if total_memory is not None:
            self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, self.total_memory)]

    def allocate(self, process_id: str, size: int, algorithm: str) -> tuple[bool, str]:
        if size <= 0:
            return False, "Size must be positive."
        if any(block.process_id == process_id for block in self.blocks):
            return False, f"{process_id} already exists."

        free_blocks = [block for block in self.blocks if block.is_free and block.size >= size]
        if not free_blocks:
            return False, "Allocation failed: no block large enough."

        if algorithm == "First Fit":
            target = free_blocks[0]
        elif algorithm == "Best Fit":
            target = min(free_blocks, key=lambda block: block.size)
        else:
            target = max(free_blocks, key=lambda block: block.size)

        index = self.blocks.index(target)
        allocated = MemoryBlock(target.start, size, process_id, process_id)
        replacement = [allocated]
        remaining = target.size - size
        if remaining:
            replacement.append(MemoryBlock(target.start + size, remaining))
        self.blocks[index:index + 1] = replacement
        return True, f"Allocated {size} units to {process_id} using {algorithm}."

    def deallocate(self, process_id: str) -> tuple[bool, str]:
        found = False
        for block in self.blocks:
            if block.process_id == process_id:
                block.process_id = None
                block.label = "Free"
                found = True
        if not found:
            return False, f"{process_id} not found."
        self._merge_free_blocks()
        return True, f"Released memory for {process_id}."

    def _merge_free_blocks(self) -> None:
        merged: list[MemoryBlock] = []
        for block in self.blocks:
            if merged and merged[-1].is_free and block.is_free:
                merged[-1].size += block.size
            else:
                merged.append(MemoryBlock(block.start, block.size, block.process_id, block.label))
        start = 0
        for block in merged:
            block.start = start
            start += block.size
        self.blocks = merged

    def metrics(self) -> dict[str, int]:
        used = sum(block.size for block in self.blocks if not block.is_free)
        total_free = self.total_memory - used
        largest_free = max((block.size for block in self.blocks if block.is_free), default=0)
        external_fragmentation = max(total_free - largest_free, 0)
        return {
            "used": used,
            "free": total_free,
            "largest_free": largest_free,
            "external_fragmentation": external_fragmentation,
        }


class PagingSimulator:
    def __init__(self, frame_count: int, frame_size: int) -> None:
        self.frame_count = frame_count
        self.frame_size = frame_size
        self.reset(frame_count, frame_size)

    def reset(self, frame_count: int | None = None, frame_size: int | None = None) -> None:
        if frame_count is not None:
            self.frame_count = frame_count
        if frame_size is not None:
            self.frame_size = frame_size
        self.frames = [FrameSlot() for _ in range(self.frame_count)]
        self.processes: dict[str, int] = {}
        self.page_tables: dict[str, dict[int, int]] = {}
        self.clock = 0
        self.page_faults = 0
        self.accesses = 0

    def create_process(self, process_id: str, page_count: int) -> tuple[bool, str]:
        if page_count <= 0:
            return False, "Page count must be positive."
        if process_id in self.processes:
            return False, f"{process_id} already exists."
        self.processes[process_id] = page_count
        self.page_tables[process_id] = {}
        return True, f"Created {process_id} with {page_count} pages."

    def remove_process(self, process_id: str) -> tuple[bool, str]:
        if process_id not in self.processes:
            return False, f"{process_id} not found."
        del self.processes[process_id]
        del self.page_tables[process_id]
        for frame in self.frames:
            if frame.process_id == process_id:
                frame.process_id = None
                frame.page_number = None
                frame.loaded_at = -1
                frame.last_used = -1
        return True, f"Removed {process_id} and released its frames."

    def access_page(self, process_id: str, page_number: int, algorithm: str) -> tuple[bool, str]:
        if process_id not in self.processes:
            return False, f"{process_id} not found."
        if page_number < 0 or page_number >= self.processes[process_id]:
            return False, f"Page {page_number} is out of range for {process_id}."

        self.clock += 1
        self.accesses += 1
        table = self.page_tables[process_id]
        if page_number in table:
            frame_index = table[page_number]
            self.frames[frame_index].last_used = self.clock
            return True, f"Page hit: {process_id}[{page_number}] in frame {frame_index}."

        self.page_faults += 1
        free_index = next((idx for idx, frame in enumerate(self.frames) if frame.is_free), None)
        if free_index is None:
            free_index = self._pick_victim(algorithm)
            victim = self.frames[free_index]
            victim_table = self.page_tables[victim.process_id]
            del victim_table[victim.page_number]
            action = (
                f"Page fault: replaced {victim.process_id}[{victim.page_number}] "
                f"from frame {free_index} using {algorithm}."
            )
        else:
            action = f"Page fault: loaded into free frame {free_index}."

        self.frames[free_index] = FrameSlot(process_id, page_number, self.clock, self.clock)
        self.page_tables[process_id][page_number] = free_index
        return True, f"{action} Now serving {process_id}[{page_number}]."

    def _pick_victim(self, algorithm: str) -> int:
        if algorithm == "FIFO":
            return min(range(len(self.frames)), key=lambda idx: self.frames[idx].loaded_at)
        return min(range(len(self.frames)), key=lambda idx: self.frames[idx].last_used)

    def metrics(self) -> dict[str, float]:
        used_frames = sum(1 for frame in self.frames if not frame.is_free)
        utilization = (used_frames / self.frame_count) * 100 if self.frame_count else 0
        fault_rate = (self.page_faults / self.accesses) * 100 if self.accesses else 0
        return {
            "used_frames": used_frames,
            "page_faults": self.page_faults,
            "accesses": self.accesses,
            "utilization": utilization,
            "fault_rate": fault_rate,
        }


class SegmentationSimulator:
    def __init__(self, total_memory: int) -> None:
        self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, total_memory)]
        self.segment_tables: dict[str, list[tuple[str, int, int]]] = {}

    def reset(self, total_memory: int | None = None) -> None:
        if total_memory is not None:
            self.total_memory = total_memory
        self.blocks = [MemoryBlock(0, self.total_memory)]
        self.segment_tables = {}

    def allocate_process(self, process_id: str, segments: list[tuple[str, int]]) -> tuple[bool, str]:
        if process_id in self.segment_tables:
            return False, f"{process_id} already exists."
        for _, size in segments:
            if size <= 0:
                return False, "All segment sizes must be positive."

        allocated_entries: list[tuple[str, int, int]] = []
        for segment_name, size in segments:
            block_index = self._find_first_fit(size)
            if block_index is None:
                self._rollback(process_id)
                return False, f"Failed to allocate segment {segment_name}; not enough contiguous space."
            block = self.blocks[block_index]
            base = block.start
            label = f"{process_id}:{segment_name}"
            replacement = [MemoryBlock(base, size, process_id, label)]
            remaining = block.size - size
            if remaining:
                replacement.append(MemoryBlock(base + size, remaining))
            self.blocks[block_index:block_index + 1] = replacement
            allocated_entries.append((segment_name, base, size))
        self.segment_tables[process_id] = allocated_entries
        return True, f"Allocated segments for {process_id}."

    def _rollback(self, process_id: str) -> None:
        for block in self.blocks:
            if block.process_id == process_id:
                block.process_id = None
                block.label = "Free"
        self._merge_free_blocks()
        self.segment_tables.pop(process_id, None)

    def _find_first_fit(self, size: int) -> int | None:
        for index, block in enumerate(self.blocks):
            if block.is_free and block.size >= size:
                return index
        return None

    def deallocate_process(self, process_id: str) -> tuple[bool, str]:
        if process_id not in self.segment_tables:
            return False, f"{process_id} not found."
        for block in self.blocks:
            if block.process_id == process_id:
                block.process_id = None
                block.label = "Free"
        del self.segment_tables[process_id]
        self._merge_free_blocks()
        return True, f"Removed all segments for {process_id}."

    def _merge_free_blocks(self) -> None:
        merged: list[MemoryBlock] = []
        for block in self.blocks:
            if merged and merged[-1].is_free and block.is_free:
                merged[-1].size += block.size
            else:
                merged.append(MemoryBlock(block.start, block.size, block.process_id, block.label))
        start = 0
        for block in merged:
            block.start = start
            start += block.size
        self.blocks = merged

    def metrics(self) -> dict[str, int]:
        used = sum(block.size for block in self.blocks if not block.is_free)
        total_free = self.total_memory - used
        largest_free = max((block.size for block in self.blocks if block.is_free), default=0)
        internal_fragmentation = sum((4 - (entry[2] % 4)) % 4 for entries in self.segment_tables.values() for entry in entries)
        return {
            "used": used,
            "free": total_free,
            "largest_free": largest_free,
            "external_fragmentation": max(total_free - largest_free, 0),
            "internal_fragmentation": internal_fragmentation,
        }


class TrackerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Real-Time Memory Allocation Tracker")
        self.root.geometry("1320x860")
        self.root.minsize(1180, 760)
        self.root.configure(bg=THEME["bg"])

        self.contiguous = ContiguousMemorySimulator(256)
        self.paging = PagingSimulator(frame_count=12, frame_size=16)
        self.segmentation = SegmentationSimulator(256)

        self.contiguous_counter = 1
        self.paging_counter = 1
        self.segment_counter = 1
        self.contiguous_running = False
        self.paging_running = False
        self.segment_running = False

        self._configure_styles()
        self._build_layout()
        self.refresh_all_views()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        style.configure(".", font=("Segoe UI", 10))
        style.configure("Shell.TFrame", background=THEME["bg"])
        style.configure("Card.TFrame", background=THEME["panel"])
        style.configure("Panel.TFrame", background=THEME["panel_alt"])
        style.configure("Card.TLabelframe", background=THEME["panel"], foreground=THEME["text"])
        style.configure("Card.TLabelframe.Label", background=THEME["panel"], foreground=THEME["text"], font=("Segoe UI", 10, "bold"))
        style.configure("HeroTitle.TLabel", background=THEME["bg"], foreground=THEME["text"], font=("Segoe UI Semibold", 22))
        style.configure("HeroSub.TLabel", background=THEME["bg"], foreground=THEME["muted"], font=("Segoe UI", 10))
        style.configure("SectionTitle.TLabel", background=THEME["panel"], foreground=THEME["surface"], font=("Segoe UI Semibold", 12))
        style.configure("Body.TLabel", background=THEME["panel"], foreground=THEME["text"])
        style.configure("Muted.TLabel", background=THEME["panel"], foreground=THEME["muted"])
        style.configure("Chip.TLabel", background=THEME["panel_alt"], foreground=THEME["surface"], padding=(10, 4), font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("!disabled", THEME["accent"])], foreground=[("!disabled", "#06101c")])
        style.configure("Tracker.TNotebook", background=THEME["bg"], borderwidth=0)
        style.configure("Tracker.TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10, "bold"))
        style.configure("Tracker.Treeview", rowheight=28)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell = ttk.Frame(self.root, padding=16, style="Shell.TFrame")
        shell.grid(sticky="nsew")
        shell.columnconfigure(0, weight=5)
        shell.columnconfigure(1, weight=2)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Shell.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="Real-Time Memory Allocation Tracker", style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="CSE316 Operating System | Section 2E048 | Topic: paging, segmentation, fragmentation, and page faults",
            style="HeroSub.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        chip_bar = ttk.Frame(header, style="Shell.TFrame")
        chip_bar.grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(chip_bar, text="Himanshu Singh | Roll 48", style="Chip.TLabel").grid(row=0, column=0, padx=(0, 8))
        ttk.Label(chip_bar, text="Subhang Sharma | Roll 47", style="Chip.TLabel").grid(row=0, column=1, padx=(0, 8))
        ttk.Label(chip_bar, text="Lovely Professional University", style="Chip.TLabel").grid(row=0, column=2)

        main_panel = ttk.Frame(shell, style="Card.TFrame", padding=10)
        main_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        main_panel.columnconfigure(0, weight=1)
        main_panel.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main_panel, style="Tracker.TNotebook")
        self.notebook.grid(row=0, column=0, sticky="nsew")

        sidebar = ttk.Frame(shell, style="Card.TFrame", padding=12)
        sidebar.grid(row=1, column=1, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)

        ttk.Label(sidebar, text="Presentation Companion", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        notes = (
            "Use Sample Load to create an instant scenario.\n"
            "Use Auto Demo for the video to show real-time updates.\n"
            "Explain fragmentation in the Contiguous tab, page faults in Paging, "
            "and base-limit mapping in Segmentation."
        )
        ttk.Label(sidebar, text=notes, style="Muted.TLabel", wraplength=300, justify="left").grid(row=1, column=0, sticky="new", pady=(8, 14))

        log_card = ttk.LabelFrame(sidebar, text="Session Log", style="Card.TLabelframe", padding=8)
        log_card.grid(row=2, column=0, sticky="nsew")
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(0, weight=1)
        self.log_text = tk.Text(
            log_card,
            width=40,
            state="disabled",
            wrap="word",
            bg=THEME["panel_alt"],
            fg=THEME["text"],
            insertbackground=THEME["surface"],
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        self._build_contiguous_tab()
        self._build_paging_tab()
        self._build_segmentation_tab()

    def _build_contiguous_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12, style="Card.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Contiguous Allocation")

        ttk.Label(
            tab,
            text="Simulate First Fit, Best Fit, and Worst Fit while tracking external fragmentation.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controls = ttk.LabelFrame(tab, text="Controls", style="Card.TLabelframe", padding=10)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        self.contiguous_memory_var = tk.StringVar(value="256")
        self.contiguous_pid_var = tk.StringVar(value="P1")
        self.contiguous_size_var = tk.StringVar(value="40")
        self.contiguous_algorithm_var = tk.StringVar(value="First Fit")

        ttk.Label(controls, text="Total Memory").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.contiguous_memory_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="Apply Size", command=self.apply_contiguous_size).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(controls, text="Process ID").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.contiguous_pid_var).grid(row=1, column=1, sticky="ew", pady=3)

        ttk.Label(controls, text="Memory Needed").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.contiguous_size_var).grid(row=2, column=1, sticky="ew", pady=3)

        ttk.Label(controls, text="Algorithm").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(
            controls,
            textvariable=self.contiguous_algorithm_var,
            values=["First Fit", "Best Fit", "Worst Fit"],
            state="readonly",
        ).grid(row=3, column=1, sticky="ew", pady=3)

        buttons = ttk.Frame(controls)
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for idx in range(5):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="Allocate", command=self.allocate_contiguous).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(buttons, text="Deallocate", command=self.deallocate_contiguous).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(buttons, text="Auto Demo", command=self.toggle_contiguous_auto).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(buttons, text="Sample Load", command=self.seed_contiguous_demo).grid(row=0, column=3, sticky="ew", padx=2)
        ttk.Button(buttons, text="Reset", command=self.reset_contiguous).grid(row=0, column=4, sticky="ew", padx=2)

        metrics = ttk.LabelFrame(tab, text="Metrics", style="Card.TLabelframe", padding=10)
        metrics.grid(row=1, column=1, sticky="nsew", pady=(0, 10))
        self.contiguous_metrics_var = tk.StringVar()
        ttk.Label(metrics, textvariable=self.contiguous_metrics_var, justify="left").grid(sticky="w")

        viz = ttk.LabelFrame(tab, text="Memory Map", style="Card.TLabelframe", padding=10)
        viz.grid(row=2, column=0, columnspan=2, sticky="nsew")
        viz.columnconfigure(0, weight=1)
        viz.rowconfigure(0, weight=1)
        self.contiguous_canvas = tk.Canvas(viz, bg=THEME["panel_alt"], height=360, highlightthickness=0)
        self.contiguous_canvas.grid(sticky="nsew")

    def _build_paging_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12, style="Card.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Paging")

        ttk.Label(
            tab,
            text="Track page requests, faults, and replacement decisions in real time.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controls = ttk.LabelFrame(tab, text="Controls", style="Card.TLabelframe", padding=10)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        self.frame_count_var = tk.StringVar(value="12")
        self.frame_size_var = tk.StringVar(value="16")
        self.paging_pid_var = tk.StringVar(value="PR1")
        self.page_count_var = tk.StringVar(value="5")
        self.page_access_var = tk.StringVar(value="0")
        self.replacement_var = tk.StringVar(value="FIFO")

        ttk.Label(controls, text="Frame Count").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.frame_count_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Frame Size").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.frame_size_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="Apply Setup", command=self.apply_paging_setup).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        ttk.Label(controls, text="Process ID").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.paging_pid_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Page Count").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.page_count_var).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Page Access").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.page_access_var).grid(row=4, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Replacement").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(
            controls,
            textvariable=self.replacement_var,
            values=["FIFO", "LRU"],
            state="readonly",
        ).grid(row=5, column=1, sticky="ew", pady=3)

        buttons = ttk.Frame(controls)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for idx in range(6):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="Create Proc", command=self.create_paging_process).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(buttons, text="Access Page", command=self.access_paging_page).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(buttons, text="Remove Proc", command=self.remove_paging_process).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(buttons, text="Auto Demo", command=self.toggle_paging_auto).grid(row=0, column=3, sticky="ew", padx=2)
        ttk.Button(buttons, text="Sample Load", command=self.seed_paging_demo).grid(row=0, column=4, sticky="ew", padx=2)
        ttk.Button(buttons, text="Reset", command=self.reset_paging).grid(row=0, column=5, sticky="ew", padx=2)

        metrics = ttk.LabelFrame(tab, text="Metrics", style="Card.TLabelframe", padding=10)
        metrics.grid(row=1, column=1, sticky="nsew", pady=(0, 10))
        self.paging_metrics_var = tk.StringVar()
        ttk.Label(metrics, textvariable=self.paging_metrics_var, justify="left").grid(sticky="w")

        viz = ttk.Panedwindow(tab, orient="horizontal")
        viz.grid(row=2, column=0, columnspan=2, sticky="nsew")

        frame_panel = ttk.LabelFrame(viz, text="Frames", style="Card.TLabelframe", padding=10)
        frame_panel.columnconfigure(0, weight=1)
        frame_panel.rowconfigure(0, weight=1)
        self.paging_canvas = tk.Canvas(frame_panel, bg=THEME["panel_alt"], height=360, highlightthickness=0)
        self.paging_canvas.grid(sticky="nsew")
        viz.add(frame_panel, weight=2)

        table_panel = ttk.LabelFrame(viz, text="Page Tables", style="Card.TLabelframe", padding=10)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(0, weight=1)
        self.page_table = ttk.Treeview(table_panel, columns=("process", "page", "frame"), show="headings", height=14, style="Tracker.Treeview")
        for column in ("process", "page", "frame"):
            self.page_table.heading(column, text=column.title())
            self.page_table.column(column, width=90, anchor="center")
        self.page_table.grid(sticky="nsew")
        viz.add(table_panel, weight=1)

    def _build_segmentation_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12, style="Card.TFrame")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)
        self.notebook.add(tab, text="Segmentation")

        ttk.Label(
            tab,
            text="Visualize code, data, and stack segments with base and limit mappings.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controls = ttk.LabelFrame(tab, text="Controls", style="Card.TLabelframe", padding=10)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        self.segment_memory_var = tk.StringVar(value="256")
        self.segment_pid_var = tk.StringVar(value="S1")
        self.code_size_var = tk.StringVar(value="32")
        self.data_size_var = tk.StringVar(value="20")
        self.stack_size_var = tk.StringVar(value="24")

        ttk.Label(controls, text="Total Memory").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.segment_memory_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(controls, text="Apply Size", command=self.apply_segment_size).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(controls, text="Process ID").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.segment_pid_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Code Size").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.code_size_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Data Size").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.data_size_var).grid(row=3, column=1, sticky="ew", pady=3)
        ttk.Label(controls, text="Stack Size").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.stack_size_var).grid(row=4, column=1, sticky="ew", pady=3)

        buttons = ttk.Frame(controls)
        buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for idx in range(5):
            buttons.columnconfigure(idx, weight=1)
        ttk.Button(buttons, text="Allocate", command=self.allocate_segments).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(buttons, text="Deallocate", command=self.deallocate_segments).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(buttons, text="Auto Demo", command=self.toggle_segment_auto).grid(row=0, column=2, sticky="ew", padx=2)
        ttk.Button(buttons, text="Sample Load", command=self.seed_segment_demo).grid(row=0, column=3, sticky="ew", padx=2)
        ttk.Button(buttons, text="Reset", command=self.reset_segments).grid(row=0, column=4, sticky="ew", padx=2)

        metrics = ttk.LabelFrame(tab, text="Metrics", style="Card.TLabelframe", padding=10)
        metrics.grid(row=1, column=1, sticky="nsew", pady=(0, 10))
        self.segment_metrics_var = tk.StringVar()
        ttk.Label(metrics, textvariable=self.segment_metrics_var, justify="left").grid(sticky="w")

        viz = ttk.Panedwindow(tab, orient="horizontal")
        viz.grid(row=2, column=0, columnspan=2, sticky="nsew")

        memory_panel = ttk.LabelFrame(viz, text="Segmented Memory", style="Card.TLabelframe", padding=10)
        memory_panel.columnconfigure(0, weight=1)
        memory_panel.rowconfigure(0, weight=1)
        self.segment_canvas = tk.Canvas(memory_panel, bg=THEME["panel_alt"], height=360, highlightthickness=0)
        self.segment_canvas.grid(sticky="nsew")
        viz.add(memory_panel, weight=2)

        table_panel = ttk.LabelFrame(viz, text="Segment Table", style="Card.TLabelframe", padding=10)
        table_panel.columnconfigure(0, weight=1)
        table_panel.rowconfigure(0, weight=1)
        self.segment_table = ttk.Treeview(table_panel, columns=("process", "segment", "base", "limit"), show="headings", height=14, style="Tracker.Treeview")
        for column in ("process", "segment", "base", "limit"):
            self.segment_table.heading(column, text=column.title())
            self.segment_table.column(column, width=90, anchor="center")
        self.segment_table.grid(sticky="nsew")
        viz.add(table_panel, weight=1)

    def parse_positive_int(self, value: str, field_name: str) -> int | None:
        try:
            parsed = int(value)
        except ValueError:
            messagebox.showerror("Invalid Input", f"{field_name} must be an integer.")
            return None
        if parsed <= 0:
            messagebox.showerror("Invalid Input", f"{field_name} must be positive.")
            return None
        return parsed

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def refresh_all_views(self) -> None:
        self.refresh_contiguous_view()
        self.refresh_paging_view()
        self.refresh_segment_view()

    def refresh_contiguous_view(self) -> None:
        metrics = self.contiguous.metrics()
        self.contiguous_metrics_var.set(
            "\n".join(
                [
                    f"Used Memory: {metrics['used']} units",
                    f"Free Memory: {metrics['free']} units",
                    f"Largest Free Block: {metrics['largest_free']} units",
                    f"External Fragmentation: {metrics['external_fragmentation']} units",
                ]
            )
        )
        self.draw_memory_blocks(self.contiguous_canvas, self.contiguous.blocks, self.contiguous.total_memory)

    def refresh_paging_view(self) -> None:
        metrics = self.paging.metrics()
        self.paging_metrics_var.set(
            "\n".join(
                [
                    f"Used Frames: {metrics['used_frames']} / {self.paging.frame_count}",
                    f"Frame Size: {self.paging.frame_size} units",
                    f"Page Faults: {metrics['page_faults']}",
                    f"Memory Accesses: {metrics['accesses']}",
                    f"Utilization: {metrics['utilization']:.1f}%",
                    f"Fault Rate: {metrics['fault_rate']:.1f}%",
                ]
            )
        )
        self.draw_frames()
        for row in self.page_table.get_children():
            self.page_table.delete(row)
        for process_id, mapping in sorted(self.paging.page_tables.items()):
            for page_number, frame_index in sorted(mapping.items()):
                self.page_table.insert("", "end", values=(process_id, page_number, frame_index))

    def refresh_segment_view(self) -> None:
        metrics = self.segmentation.metrics()
        self.segment_metrics_var.set(
            "\n".join(
                [
                    f"Used Memory: {metrics['used']} units",
                    f"Free Memory: {metrics['free']} units",
                    f"Largest Free Block: {metrics['largest_free']} units",
                    f"External Fragmentation: {metrics['external_fragmentation']} units",
                    f"Estimated Internal Fragmentation: {metrics['internal_fragmentation']} units",
                ]
            )
        )
        self.draw_memory_blocks(self.segment_canvas, self.segmentation.blocks, self.segmentation.total_memory)
        for row in self.segment_table.get_children():
            self.segment_table.delete(row)
        for process_id, entries in sorted(self.segmentation.segment_tables.items()):
            for segment_name, base, limit in entries:
                self.segment_table.insert("", "end", values=(process_id, segment_name, base, limit))

    def draw_memory_blocks(self, canvas: tk.Canvas, blocks: list[MemoryBlock], total_memory: int) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 800)
        height = max(canvas.winfo_height(), 320)
        margin = 28
        usable_width = width - (margin * 2)
        current_x = margin
        top = 75
        rect_height = 120

        canvas.create_text(margin, 28, text="Memory Layout", anchor="w", font=("Segoe UI", 14, "bold"), fill=THEME["surface"])
        canvas.create_text(margin, 48, text=f"Total memory: {total_memory} units", anchor="w", fill=THEME["muted"])

        for block in blocks:
            ratio = block.size / total_memory if total_memory else 0
            block_width = max(40, usable_width * ratio)
            x1, y1 = current_x, top
            x2, y2 = current_x + block_width, top + rect_height
            fill = THEME["free_light"] if block.is_free else color_for(block.label)
            canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=THEME["bg"], width=2)
            canvas.create_text((x1 + x2) / 2, y1 + 36, text=block.label, font=("Segoe UI", 10, "bold"), width=block_width - 10, fill="#06101c")
            canvas.create_text((x1 + x2) / 2, y1 + 72, text=f"Start {block.start}\nSize {block.size}", width=block_width - 10)
            current_x = x2
        legend_y = top + rect_height + 28
        canvas.create_rectangle(margin, legend_y, margin + 18, legend_y + 18, fill=THEME["free_light"], outline="")
        canvas.create_text(margin + 26, legend_y + 9, text="Free block", anchor="w", fill=THEME["muted"])
        canvas.create_rectangle(margin + 120, legend_y, margin + 138, legend_y + 18, fill=PALETTE[0], outline="")
        canvas.create_text(margin + 146, legend_y + 9, text="Allocated block", anchor="w", fill=THEME["muted"])

    def draw_frames(self) -> None:
        canvas = self.paging_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 800)
        margin = 28
        canvas.create_text(margin, 28, text="Frame View", anchor="w", font=("Segoe UI", 14, "bold"), fill=THEME["surface"])
        canvas.create_text(
            margin,
            48,
            text=f"{self.paging.frame_count} frames, each {self.paging.frame_size} units",
            anchor="w",
            fill=THEME["muted"],
        )

        columns = 4
        box_width = (width - (margin * 2) - 18 * (columns - 1)) / columns
        box_height = 90
        for index, frame in enumerate(self.paging.frames):
            row = index // columns
            col = index % columns
            x1 = margin + col * (box_width + 18)
            y1 = 80 + row * (box_height + 18)
            x2 = x1 + box_width
            y2 = y1 + box_height
            label = "Free" if frame.is_free else f"{frame.process_id}\nPage {frame.page_number}"
            fill = THEME["free_light"] if frame.is_free else color_for(frame.process_id or "Free")
            canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=THEME["bg"], width=2)
            canvas.create_text((x1 + x2) / 2, y1 + 16, text=f"Frame {index}", font=("Segoe UI", 10, "bold"), fill="#06101c")
            canvas.create_text((x1 + x2) / 2, y1 + 50, text=label, width=box_width - 12, fill="#06101c")

    def apply_contiguous_size(self) -> None:
        total_memory = self.parse_positive_int(self.contiguous_memory_var.get(), "Total Memory")
        if total_memory is None:
            return
        self.contiguous.reset(total_memory)
        self.contiguous_counter = 1
        self.log(f"Contiguous memory reset to {total_memory} units.")
        self.refresh_contiguous_view()

    def allocate_contiguous(self) -> None:
        size = self.parse_positive_int(self.contiguous_size_var.get(), "Memory Needed")
        if size is None:
            return
        process_id = self.contiguous_pid_var.get().strip() or f"P{self.contiguous_counter}"
        ok, message = self.contiguous.allocate(process_id, size, self.contiguous_algorithm_var.get())
        self.log(message)
        if ok:
            self.contiguous_counter += 1
            self.contiguous_pid_var.set(f"P{self.contiguous_counter}")
        self.refresh_contiguous_view()

    def deallocate_contiguous(self) -> None:
        process_id = self.contiguous_pid_var.get().strip()
        if not process_id:
            messagebox.showerror("Missing Process ID", "Enter the process ID to release.")
            return
        _, message = self.contiguous.deallocate(process_id)
        self.log(message)
        self.refresh_contiguous_view()

    def seed_contiguous_demo(self) -> None:
        self.reset_contiguous()
        for process_id, size in [("P1", 40), ("P2", 28), ("P3", 64), ("P4", 36)]:
            self.contiguous.allocate(process_id, size, "First Fit")
        self.contiguous.deallocate("P2")
        self.log("Loaded a sample contiguous allocation scenario.")
        self.refresh_contiguous_view()

    def reset_contiguous(self) -> None:
        total_memory = self.parse_positive_int(self.contiguous_memory_var.get(), "Total Memory")
        if total_memory is None:
            return
        self.contiguous_running = False
        self.contiguous.reset(total_memory)
        self.contiguous_counter = 1
        self.contiguous_pid_var.set("P1")
        self.log("Reset contiguous allocation simulator.")
        self.refresh_contiguous_view()

    def toggle_contiguous_auto(self) -> None:
        self.contiguous_running = not self.contiguous_running
        self.log("Contiguous auto demo started." if self.contiguous_running else "Contiguous auto demo paused.")
        if self.contiguous_running:
            self.run_contiguous_auto()

    def run_contiguous_auto(self) -> None:
        if not self.contiguous_running:
            return
        active = [block.process_id for block in self.contiguous.blocks if block.process_id]
        if active and random.random() < 0.4:
            process_id = random.choice(active)
            _, message = self.contiguous.deallocate(process_id)
        else:
            process_id = f"P{self.contiguous_counter}"
            size = random.randint(12, 72)
            ok, message = self.contiguous.allocate(process_id, size, self.contiguous_algorithm_var.get())
            if ok:
                self.contiguous_counter += 1
        self.log(message)
        self.refresh_contiguous_view()
        self.root.after(1100, self.run_contiguous_auto)

    def apply_paging_setup(self) -> None:
        frame_count = self.parse_positive_int(self.frame_count_var.get(), "Frame Count")
        frame_size = self.parse_positive_int(self.frame_size_var.get(), "Frame Size")
        if frame_count is None or frame_size is None:
            return
        self.paging.reset(frame_count, frame_size)
        self.paging_counter = 1
        self.log(f"Paging setup updated: {frame_count} frames of size {frame_size}.")
        self.refresh_paging_view()

    def create_paging_process(self) -> None:
        page_count = self.parse_positive_int(self.page_count_var.get(), "Page Count")
        if page_count is None:
            return
        process_id = self.paging_pid_var.get().strip() or f"PR{self.paging_counter}"
        ok, message = self.paging.create_process(process_id, page_count)
        self.log(message)
        if ok:
            self.paging_counter += 1
            self.paging_pid_var.set(f"PR{self.paging_counter}")
        self.refresh_paging_view()

    def access_paging_page(self) -> None:
        try:
            page_number = int(self.page_access_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Page Access must be an integer.")
            return
        process_id = self.paging_pid_var.get().strip()
        if not process_id:
            messagebox.showerror("Missing Process ID", "Enter the process ID to access.")
            return
        ok, message = self.paging.access_page(process_id, page_number, self.replacement_var.get())
        self.log(message)
        if ok and process_id in self.paging.processes:
            next_page = (page_number + 1) % self.paging.processes[process_id]
            self.page_access_var.set(str(next_page))
        self.refresh_paging_view()

    def remove_paging_process(self) -> None:
        process_id = self.paging_pid_var.get().strip()
        if not process_id:
            messagebox.showerror("Missing Process ID", "Enter the process ID to remove.")
            return
        _, message = self.paging.remove_process(process_id)
        self.log(message)
        self.refresh_paging_view()

    def seed_paging_demo(self) -> None:
        self.reset_paging()
        for process_id, page_count in [("PR1", 4), ("PR2", 3), ("PR3", 5)]:
            self.paging.create_process(process_id, page_count)
        for process_id, page in [("PR1", 0), ("PR1", 1), ("PR2", 0), ("PR3", 0), ("PR1", 2), ("PR2", 1)]:
            self.paging.access_page(process_id, page, self.replacement_var.get())
        self.log("Loaded a sample paging scenario.")
        self.refresh_paging_view()

    def reset_paging(self) -> None:
        frame_count = self.parse_positive_int(self.frame_count_var.get(), "Frame Count")
        frame_size = self.parse_positive_int(self.frame_size_var.get(), "Frame Size")
        if frame_count is None or frame_size is None:
            return
        self.paging_running = False
        self.paging.reset(frame_count, frame_size)
        self.paging_counter = 1
        self.paging_pid_var.set("PR1")
        self.page_access_var.set("0")
        self.log("Reset paging simulator.")
        self.refresh_paging_view()

    def toggle_paging_auto(self) -> None:
        self.paging_running = not self.paging_running
        self.log("Paging auto demo started." if self.paging_running else "Paging auto demo paused.")
        if self.paging_running:
            self.run_paging_auto()

    def run_paging_auto(self) -> None:
        if not self.paging_running:
            return
        if not self.paging.processes or random.random() < 0.3:
            process_id = f"PR{self.paging_counter}"
            page_count = random.randint(3, 7)
            ok, message = self.paging.create_process(process_id, page_count)
            if ok:
                self.paging_counter += 1
        elif random.random() < 0.2 and len(self.paging.processes) > 1:
            process_id = random.choice(list(self.paging.processes))
            _, message = self.paging.remove_process(process_id)
        else:
            process_id = random.choice(list(self.paging.processes))
            page_number = random.randint(0, self.paging.processes[process_id] - 1)
            _, message = self.paging.access_page(process_id, page_number, self.replacement_var.get())
        self.log(message)
        self.refresh_paging_view()
        self.root.after(1000, self.run_paging_auto)

    def apply_segment_size(self) -> None:
        total_memory = self.parse_positive_int(self.segment_memory_var.get(), "Total Memory")
        if total_memory is None:
            return
        self.segmentation.reset(total_memory)
        self.segment_counter = 1
        self.log(f"Segmentation memory reset to {total_memory} units.")
        self.refresh_segment_view()

    def allocate_segments(self) -> None:
        code_size = self.parse_positive_int(self.code_size_var.get(), "Code Size")
        data_size = self.parse_positive_int(self.data_size_var.get(), "Data Size")
        stack_size = self.parse_positive_int(self.stack_size_var.get(), "Stack Size")
        if None in (code_size, data_size, stack_size):
            return
        process_id = self.segment_pid_var.get().strip() or f"S{self.segment_counter}"
        segments = [("Code", code_size), ("Data", data_size), ("Stack", stack_size)]
        ok, message = self.segmentation.allocate_process(process_id, segments)
        self.log(message)
        if ok:
            self.segment_counter += 1
            self.segment_pid_var.set(f"S{self.segment_counter}")
        self.refresh_segment_view()

    def deallocate_segments(self) -> None:
        process_id = self.segment_pid_var.get().strip()
        if not process_id:
            messagebox.showerror("Missing Process ID", "Enter the process ID to remove.")
            return
        _, message = self.segmentation.deallocate_process(process_id)
        self.log(message)
        self.refresh_segment_view()

    def seed_segment_demo(self) -> None:
        self.reset_segments()
        demo_processes = {
            "S1": [("Code", 28), ("Data", 18), ("Stack", 20)],
            "S2": [("Code", 32), ("Data", 16), ("Stack", 24)],
            "S3": [("Code", 22), ("Data", 14), ("Stack", 18)],
        }
        for process_id, segments in demo_processes.items():
            self.segmentation.allocate_process(process_id, segments)
        self.segmentation.deallocate_process("S2")
        self.log("Loaded a sample segmentation scenario.")
        self.refresh_segment_view()

    def reset_segments(self) -> None:
        total_memory = self.parse_positive_int(self.segment_memory_var.get(), "Total Memory")
        if total_memory is None:
            return
        self.segment_running = False
        self.segmentation.reset(total_memory)
        self.segment_counter = 1
        self.segment_pid_var.set("S1")
        self.log("Reset segmentation simulator.")
        self.refresh_segment_view()

    def toggle_segment_auto(self) -> None:
        self.segment_running = not self.segment_running
        self.log("Segmentation auto demo started." if self.segment_running else "Segmentation auto demo paused.")
        if self.segment_running:
            self.run_segment_auto()

    def run_segment_auto(self) -> None:
        if not self.segment_running:
            return
        if self.segmentation.segment_tables and random.random() < 0.35:
            process_id = random.choice(list(self.segmentation.segment_tables))
            _, message = self.segmentation.deallocate_process(process_id)
        else:
            process_id = f"S{self.segment_counter}"
            segments = [
                ("Code", random.randint(16, 36)),
                ("Data", random.randint(12, 28)),
                ("Stack", random.randint(12, 28)),
            ]
            ok, message = self.segmentation.allocate_process(process_id, segments)
            if ok:
                self.segment_counter += 1
        self.log(message)
        self.refresh_segment_view()
        self.root.after(1200, self.run_segment_auto)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = TrackerApp(root)
    app.log("Memory tracker ready. Use the tabs to explore contiguous allocation, paging, and segmentation.")
    root.mainloop()


if __name__ == "__main__":
    main()