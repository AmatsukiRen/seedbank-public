from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Slot


class Rows(QAbstractListModel):
    EntryRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def roleNames(self):
        return {self.EntryRole: b"entry"}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self.rows) and role == self.EntryRole:
            return self.rows[index.row()]
        return None

    @Slot(int, result="QVariantMap")
    def get(self, index):
        return self.rows[index] if 0 <= index < len(self.rows) else {}

    def replace(self, rows):
        rows = list(rows)
        if rows == self.rows:
            return False
        previous = len(self.rows)
        prefix = 0
        while prefix < min(previous, len(rows)) and rows[prefix] == self.rows[prefix]:
            prefix += 1
        difference = len(rows) - previous
        if difference > 0 and rows[prefix + difference:] == self.rows[prefix:]:
            self.beginInsertRows(QModelIndex(), prefix, prefix + difference - 1)
            self.rows = rows
            self.endInsertRows()
        elif difference < 0 and self.rows[prefix - difference:] == rows[prefix:]:
            self.beginRemoveRows(QModelIndex(), prefix, prefix - difference - 1)
            self.rows = rows
            self.endRemoveRows()
        elif len(rows) == previous:
            for position, row in enumerate(rows):
                if row != self.rows[position]:
                    self.rows[position] = row
                    index = self.index(position)
                    self.dataChanged.emit(index, index, [self.EntryRole])
        else:
            self.beginResetModel()
            self.rows = rows
            self.endResetModel()
        return True
