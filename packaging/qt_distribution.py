"""Shared exclusions for unused Qt components; not a general license audit."""


def excluded_qt_entry(name):
    normalized = name.replace("\\", "/").lower()
    return "virtualkeyboard" in normalized or (
        normalized.startswith("pyside6/") and (
            "quick3d" in normalized or "/plugins/qmltooling/" in normalized or
            normalized.rsplit("/", 1)[-1] in {"qpdf.dll", "qt6pdf.dll"}
        )
    )
