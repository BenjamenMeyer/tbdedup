import asyncio
import logging
import os
import os.path

import tkinter
import tkinter.filedialog
import tkinter.ttk


from thunderbirddedup.mbox import (
    mboxfile
)
from thunderbirddedup.planner import (
    plan as tb_planner,
)
from types import SimpleNamespace


from . import (
    tview
)


# +----------------------------------------------------+
# |      +--------------+  +-----------+ +-----------+ |
# | Path | <path value> |  | Selct Btn | | Search    | |
# |      +--------------+  +-----------+ +-----------+ |
# | +------------------------------------------------+ |
# | | Tree View                                      | |
# | | root         | progress bar | |dedup btn|      | |
# | | + layer 1    | progress bar | |dedup btn|      | |
# | | | + layer 2  | progress bar | |dedup btn|      | |
# | | .....                                          | |
# | | + layer N    | progress bar | |dedup btn|      | |
# | +------------------------------------------------+ |
# | +------------------------------------------------+ |
# | | <log data>                                     | |
# | +------------------------------------------------+ |
# +----------------------------------------------------+

LOG = logging.getLogger(__name__)


class App(tkinter.Tk):

    def __init__(self):
        super().__init__()
        self.selected_directory = ""

        self.title("Thunderbird MBOX Deduplicator")
        self.geometry("1113x900")
        self.protocol("WM_DELETE_WINDOW", self.close)

        # Layouts
        master_layout = tkinter.Frame(self, bg="lightgrey", width=1100, height=900, pady=3, padx=3)
        path_layout = tkinter.Frame(master_layout, width=1100, height=100, bg="cyan")
        tree_layout = tkinter.Frame(master_layout, width=1100, height=800, bg="blue")
        plan_layout = tkinter.Frame(master_layout, width=1100, height=800, bg="pink")

        # Path Display
        self.path_var = tkinter.StringVar()
        self.path_var.trace_add("write", self._validate_path_trace)
        self.lbl_path = tkinter.Label(path_layout, text="Path")
        self.lbl_path.grid(row=0, column=0)
        self.txt_path = tkinter.Entry(path_layout, textvariable=self.path_var, width=100)
        self.txt_path.grid(row=0, column=1, columnspan=8)

        # Base Path Selection
        self.btn_path_select = tkinter.Button(path_layout, text="Select...", command=self.select_path)
        self.btn_path_select.grid(row=0, column=9)
        self.btn_search = tkinter.Button(path_layout, text="Search", command=self.search_path)
        self.btn_search.grid(row=0, column=10)
        self.btn_search["state"] = "disabled"

        self.btn_generate_plan = tkinter.Button(path_layout, text="Generate Plan", command=self.generate_plan)
        self.btn_generate_plan.grid(row=0, column=11)
        self.btn_generate_plan["state"] = "disabled"
        # self.btn_execute_plan = tkinter.Button(path_layout, text="Execute Plan", command=self.execute_plan)
        # self.btn_execute_plan.grid(row=0, column=12)
        # self.btn_execute_plan["state"] = "disabled"

        path_layout.grid(row=0, sticky="ew")

        # Tree View
        self.tv_scrollx = tkinter.ttk.Scrollbar(master_layout, orient="horizontal")
        self.tv_scrolly = tkinter.ttk.Scrollbar(tree_layout, orient="vertical")
        self.tv_filesystem = tview.TtkCheckList(
            tree_layout,
            width=1100,
            yscrollcommand=self.tv_scrolly,
            xscrollcommand=self.tv_scrollx,
        )
        self.tv_filesystem.heading("#0", text="Disk Location")
        self.tv_filesystem.column("#0", width=1100, stretch=tkinter.YES)
        tree_layout.grid(row=1, sticky="nsew")
        self.tv_filesystem.pack()

        self.lbl_plan_display = tkinter.Label(plan_layout, text="<TBD>", relief="sunken")
        self.lbl_plan_display.grid(row=0, columnspan=12, rowspan=10)
        self.lbl_plan_display.pack()

        master_layout.pack()

    def _validate_path_trace(self, *args):
        path = self.path_var.get()
        if os.path.isdir(path):
            self.selected_directory = path
            self.btn_search["state"] = "normal"
            LOG.info(f"Path is valid: {path}")
        else:
            self.btn_search["state"] = "disabled"
        # Any change to the path invalidates the current plan
        self.btn_generate_plan["state"] = "disabled"

    def select_path(self):
        # Display a file dialog and select a base path
        selected_path = tkinter.filedialog.askdirectory(mustexist=True)
        if selected_path:
            self.path_var.set(selected_path)

    def search_path(self):
        # reset the tree
        children_to_remove = self.tv_filesystem.get_children()
        for child in children_to_remove:
            self.tv_filesystem.delete(child)

        path_parenting = {}

        def clean_base(base_path, item_path):
            if item_path.startswith(base_path):
                new_path = item_path[len(base_path + os.sep):]
                LOG.info(f"[clean base] {item_path} -> {new_path}")
                return new_path
            else:
                return item_path

        # Walk the base path and build a display of all the files and folders
        for root, dirs, files in os.walk(self.selected_directory, followlinks=True):
            LOG.info(f"[{root}] Found {len(files)} files in {root}")

            root_id = (
                self.tv_filesystem.add_item(
                    clean_base(self.selected_directory, root),
                )
                if root != self.selected_directory
                else ""
            )
            path_parenting[root] = root_id

            for filename in files:
                LOG.info(f"[{root}] Found file: {filename}")
                _, extension = os.path.splitext(filename)
                if extension in (".msf",):
                    LOG.info(f"[{root}] Ignoring file with extension {extension}")
                    continue

                fully_qualified_filename = os.path.join(
                    root,
                    filename,
                )
                self.tv_filesystem.insert(
                    path_parenting[root],
                    'end',
                    text=f"{self.tv_filesystem._unchecked} {filename}",
                    tags=(fully_qualified_filename,)
                )
        self.btn_generate_plan["state"] = (
            "normal"
            if len(path_parenting)
            else "disabled"
        )

    def close(self):
        loop = asyncio.get_event_loop()
        loop.stop()
        self.destroy()

    def generate_plan(self):

        def _get_checked_children(parent_iid, checked_items):
            for child_iid in self.tv_filesystem.get_children(parent_iid):
                if self.tv_filesystem.checked(child_iid):
                    tags = self.tv_filesystem.item(child_iid, "tags")
                    if tags:
                        checked_items.append(tags[0])
                _get_checked_children(child_iid, checked_items)

        selected_files = []
        _get_checked_children("", selected_files)

        if selected_files:
            # Create a mock options object for the planner
            options = SimpleNamespace(
                limit_pattern=None,
                location=self.selected_directory
            )

            async def run_planner():
                try:
                    output_dir, mapping_file = await tb_planner.planner(options, selected_files)
                    self.lbl_plan_display.config(
                        text=f"Plan generated in: {output_dir}\nMapping file: {mapping_file}"
                    )
                except Exception as e:
                    self.lbl_plan_display.config(text=f"Error generating plan: {e}")

            asyncio.run(run_planner())
        else:
            self.lbl_plan_display.config(text="No files selected.")
