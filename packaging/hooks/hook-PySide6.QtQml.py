from pathlib import PurePath

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()
allowed = (
    "QtQml", "QtCore", "QtQuick/Controls", "QtQuick/Templates", "QtQuick/Window",
    "QtQuick/Layouts", "QtQuick/Shapes", "QtQuick/Dialogs", "QtQuick/NativeStyle",
    "Qt/labs/folderlistmodel", "Qt/labs/platform",
)


def needed(entry):
    destination = PurePath(entry[1]).as_posix().split("/qml/", 1)[-1]
    return destination == "QtQuick" or any(destination == prefix or destination.startswith(prefix + "/") for prefix in allowed)


binaries += [entry for entry in qml_binaries if needed(entry)]
datas += [entry for entry in qml_datas if needed(entry)]
