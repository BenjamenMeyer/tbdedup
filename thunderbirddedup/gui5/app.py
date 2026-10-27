"""
Copyright 2023-2026 Benjamen R. Meyer

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import asyncio
import logging
import os
import os.path

import kivy.app
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooser
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.treeview import TreeView
from kivy.uix.widget import Widget

from thunderbirddedup.mbox import (
    mboxfile,
)
from thunderbirddedup.gui5 import (
    filedialog,
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


class TheApp(BoxLayout):

    def __init__(self, **kwargs):
        # force the widget into horizontal boxing so everything goes top-down
        kwargs["orientation"] = "vertical"
        super(TheApp, self).__init__(**kwargs)
        self.selected_directory = ""

        # path layout will use vertical boxing so everything goes left to right
        self.path_layout = BoxLayout(orientation='horizontal')

        # [Path] label
        self.lbl_path = Label(text="Path")
        self.lbl_path.background_color = 'grey'
        self.path_layout.add_widget(self.lbl_path)

        # Path input box - we'll let the user type it in
        self.txt_path = TextInput(
            multiline=False,
            text=self.selected_directory,
            on_text_validate=self.validate_path
        )
        self.txt_path.background_color = 'grey'
        # probably should add something to validate the text
        # and enable/disable the buttons based on the result
        self.path_layout.add_widget(self.txt_path)

        # Select button to pop-up the File/Direction Selection dialog
        self.btn_select_path = Button(text="Select...")
        self.btn_select_path.background_color = 'grey'
        self.btn_select_path.bind(on_press=self.select_path)
        self.path_layout.add_widget(self.btn_select_path)

        # Search the path
        self.btn_search_path = Button(text="Search")
        self.btn_search_path.background_color = 'grey'
        self.btn_search_path.bind(on_press=self.search_path)
        self.btn_search_path.disabled = True
        self.path_layout.add_widget(self.btn_search_path)

        # Generate button to be used once the user has selected
        # entries in the tree view that is displaying the file system layout
        self.btn_generate_plan = Button(text="Generate Plan")
        self.btn_generate_plan.background_color = 'grey'
        self.btn_generate_plan.bind(on_press=self.generate_plan)
        self.btn_generate_plan.disabled = True
        self.path_layout.add_widget(self.btn_generate_plan)

        # splitter to be able to resize stuff
        self.splitter_path = Splitter(sizable_from="bottom")
        self.splitter_path.add_widget(self.path_layout)

        # tree view for the file system view
        self.filesystem_viewer = TreeView()
        self.filesystem_viewer.background_color = 'white'
        self.filesystem_viewer.bind(selected_node=self._on_tree_node_select)

        self.add_widget(self.splitter_path)

        self.add_widget(self.filesystem_viewer)

    def _on_tree_node_select(self, instance, value):
        # Enable generate plan button if any node is selected
        self.btn_generate_plan.disabled = (value is None)

    def validate_path(self, txt):
        value = txt.text
        if os.path.isdir(value):
            # valid
            LOG.info(f"Selection {value} is a valid path")
            self.btn_search_path.disabled = False
            self.btn_generate_plan.disabled = True  # Ensure this is disabled until search is performed
        else:
            # invalid
            LOG.info(f"Selection {value} is not a valid path")
            self.btn_search_path.disabled = True
            self.btn_generate_plan.disabled = True

    def select_path(self, btn):
        def _on_select_callback(instance, path):
            self.selected_directory = path
            self.txt_path.text = self.selected_directory
            self.validate_path(self.txt_path)
            popup.dismiss()

        def _on_cancel_callback(instance):
            popup.dismiss()

        select_directory_content = filedialog.SelectDirectory()
        select_directory_content.bind(on_submit=_on_select_callback)
        select_directory_content.bind(on_cancel=_on_cancel_callback)

        popup = Popup(
            title="Select Directory",
            content=select_directory_content,
            size_hint=(0.9, 0.9),
            auto_dismiss=False,
        )
        popup.open()

    def search_path(self, btn):
        # Clear existing TreeView nodes
        self.filesystem_viewer.clear_widgets()
        # Add a root node, which will be expanded by default to show the selected directory
        root_node = self.filesystem_viewer.add_node(
            TreeViewLabel(text=self.selected_directory, is_open=True, no_selection=True)
        )

        path_to_node = {self.selected_directory: root_node}

        # Walk the selected directory and build the TreeView
        for root, dirs, files in os.walk(self.selected_directory):
            # Sort directories and files for consistent display
            dirs.sort()
            files.sort()

            current_node = path_to_node.get(root)
            if not current_node:
                LOG.warning(f"Parent node not found for {root}")
                continue

            for d in dirs:
                dir_path = os.path.join(root, d)
                node = self.filesystem_viewer.add_node(
                    TreeViewLabel(text=d, is_open=False, file_path=dir_path), current_node
                )
                path_to_node[dir_path] = node

            for f in files:
                file_path = os.path.join(root, f)
                if f.endswith('.mbox') or f.endswith('.mbox.msf'):
                    node = self.filesystem_viewer.add_node(
                        TreeViewLabel(text=f, is_open=False, file_path=file_path), current_node
                    )

        # Initial state of the button based on selection
        self._on_tree_node_select(self.filesystem_viewer, self.filesystem_viewer.selected_node)

    def generate_plan(self, btn):
        selected_node = self.filesystem_viewer.selected_node
        if selected_node and hasattr(selected_node, 'file_path'):
            selected_file = selected_node.file_path
            msg = Popup(
                title="Generate Plan",
                content=Label(text=f"Generate Plan Clicked for: {selected_file}"),
                auto_dismiss=True,
            )
            msg.open()
        else:
            msg = Popup(
                title="Generate Plan",
                content=Label(text="No file selected for planning."),
                auto_dismiss=True,
            )
            msg.open()


class App(kivy.app.App):

    def build(self):
        return TheApp()
