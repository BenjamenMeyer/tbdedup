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
from kivy.uix.boxlayout import (
    BoxLayout,
)
from kivy.uix.floatlayout import (
    FloatLayout,
)
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooser


class SelectDirectory(FloatLayout):

    def __init__(self, **kwargs):
        super(SelectDirectory, self).__init__(**kwargs)

        # Use a main_layout to hold all components
        main_layout = BoxLayout(orientation="vertical")

        # Top buttons layout for Icon/List View
        top_buttons_layout = BoxLayout(orientation="horizontal", size_hint_y=0.1)
        self.btn_icon = Button(text="Icon View")
        self.btn_icon.bind(on_press=self.set_icon_view)
        top_buttons_layout.add_widget(self.btn_icon)

        self.btn_list = Button(text="List View")
        self.btn_list.bind(on_press=self.set_list_view)
        top_buttons_layout.add_widget(self.btn_list)
        main_layout.add_widget(top_buttons_layout)

        # FileChooser instance
        self.fc = FileChooser(
            show_hidden=True,
            dirselect=True,
            filters=['*'],
            # view_mode='list',
        )
        self.fc.view_mode = 'list'
        main_layout.add_widget(self.fc)

        # Bottom buttons layout for Select/Cancel
        bottom_buttons_layout = BoxLayout(orientation="horizontal", size_hint_y=0.1)
        self.btn_select = Button(text="Select")
        self.btn_select.bind(on_press=self._on_select)
        bottom_buttons_layout.add_widget(self.btn_select)

        self.btn_cancel = Button(text="Cancel")
        self.btn_cancel.bind(on_press=self._on_cancel)
        bottom_buttons_layout.add_widget(self.btn_cancel)
        main_layout.add_widget(bottom_buttons_layout)

        self.add_widget(main_layout)

        # Define Kivy properties for events
        self.register_event_type('on_submit')
        self.register_event_type('on_cancel')

    def _on_select(self, instance):
        self.dispatch('on_submit', self.fc.path)

    def _on_cancel(self, instance):
        self.dispatch('on_cancel')

    def on_submit(self, path):
        pass

    def on_cancel(self):
        pass

    def set_icon_view(self, instance):
        self.fc.view_mode = 'icon'

    def set_list_view(self, instance):
        self.fc.view_mode = 'list'
