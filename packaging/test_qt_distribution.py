"""Offline packaging regressions, to be run explicitly by the maintainer."""
import json
from pathlib import Path
import tempfile
import unittest

from collect_notices import copy_qt_notices
from qt_distribution import excluded_qt_entry


class QtDistributionTests(unittest.TestCase):
    def test_debug_profiler_and_gpl_runtime_are_both_excluded(self):
        for name in (
            'PySide6/plugins/qmltooling/qmldbg_quick3dprofiler.dll',
            'PySide6/plugins/qmltooling/qmldbg_debugger.dll',
            'PySide6/Qt6Quick3DUtils.dll',
            r'PySide6\Qt6Quick3DUtils.dll',
            'PySide6/qml/QtQuick3D/qmldir',
            'PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
        ):
            with self.subTest(name=name):
                self.assertTrue(excluded_qt_entry(name))

    def test_quick_2d_and_native_rendering_dependencies_remain(self):
        for name in (
            'PySide6/Qt6Quick.dll', 'PySide6/Qt6QuickControls2.dll',
            'PySide6/Qt6OpenGL.dll', 'PySide6/Qt6Qml.dll',
            'PySide6/plugins/platforms/qwindows.dll',
            'PySide6/qml/QtQuick/Shapes/qtquickshapesplugin.dll',
            'live2d/_live2d.pyd',
        ):
            with self.subTest(name=name):
                self.assertFalse(excluded_qt_entry(name))

    def test_shared_notices_include_both_license_texts_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            files = copy_qt_notices(destination, '6.12.0')
            self.assertIn('qt/LGPL-3.0-only.txt', files)
            self.assertIn('qt/GPL-3.0-only.txt', files)
            for name in files:
                self.assertTrue((destination / name).is_file())
            self.assertIn('4. Combined Works.', (destination / files[0]).read_text())
            self.assertIn('END OF TERMS AND CONDITIONS', (destination / files[1]).read_text())
            provenance = json.loads((destination / 'qt/sources.json').read_text())
            self.assertEqual(provenance['pyside_version'], '6.12.0')

    def test_dependency_upgrade_requires_new_notice_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                copy_qt_notices(Path(directory), '99.0.0')
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
