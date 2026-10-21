"""Test startup geometry without opening a GUI or loading media dependencies."""
import ast
from pathlib import Path
import tkinter as tk
import unittest


namespace = {'tk': tk}
tree = ast.parse(Path(__file__).with_name('subtitle_gui.py').read_text(encoding='utf-8-sig'))
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {'fit_window_to_screen', 'fit_main_window_to_screen'}]
exec(compile(ast.Module(body=functions, type_ignores=[]), 'subtitle_gui.py', 'exec'), namespace)


class FakeWindow:
    def __init__(self, width, height):
        self.width, self.height = width, height

    def winfo_screenwidth(self):
        return self.width

    def winfo_screenheight(self):
        return self.height

    def geometry(self, value):
        self.size = tuple(map(int, value.split('+')[0].split('x')))

    def minsize(self, width, height):
        self.minimum = (width, height)


class StartupWindowTests(unittest.TestCase):
    def test_large_display_uses_available_space(self):
        window = FakeWindow(3840, 2160)
        namespace['fit_main_window_to_screen'](window)
        self.assertEqual(window.size, (3648, 2030))

    def test_common_screens_remain_within_bounds(self):
        for width, height in [(1920,1080), (2560,1440), (1366,768)]:
            with self.subTest(screen=(width, height)):
                window = FakeWindow(width, height)
                namespace['fit_main_window_to_screen'](window)
                self.assertLessEqual(window.size[0], width - 60)
                self.assertLessEqual(window.size[1], height - 100)
                self.assertGreaterEqual(window.size[0], width * 0.9)
                self.assertTrue(all(a <= b for a,b in zip(window.minimum, window.size)))


if __name__ == '__main__':
    unittest.main()
