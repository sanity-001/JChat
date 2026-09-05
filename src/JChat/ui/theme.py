"""暗色主题 QSS（票据 006 C 方案基调）。"""

QSS = """
* { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
QMainWindow, QWidget#Root { background-color: #0f1115; }
QFrame#Card { background-color: #151923; border: 1px solid #262d3d; border-radius: 18px; }
QLabel { color: #e7ecf5; }
QLabel#Muted { color: #8b94a7; font-size: 12px; }
QLabel#Title { font-size: 17px; font-weight: 700; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPlainTextEdit#Input {
    background-color: #1b2230; color: #e7ecf5; border: 1px solid #262d3d;
    border-radius: 14px; padding: 10px 12px; font-size: 14px;
}
QPlainTextEdit#Input:focus { border: 1px solid #4f8cff; }
QPushButton#Send {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #4f8cff, stop:1 #7c5cff);
    color: white; border: none; border-radius: 14px; padding: 10px 24px; font-weight: 600;
}
QPushButton#Send:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #3f7df0, stop:1 #6c4cf0); }
QPushButton#Ghost {
    background: transparent; color: #e7ecf5; border: 1px solid #262d3d;
    border-radius: 12px; padding: 8px 14px;
}
QPushButton#Ghost:hover { border-color: #4f8cff; color: #4f8cff; }
QPushButton#Danger { background: transparent; color: #ff6b6b; border: 1px solid #6b2b2b;
    border-radius: 10px; padding: 6px 12px; }
QPushButton#Danger:hover { background: #2b1518; }
QToolTip { background-color: #1b2230; color: #e7ecf5; border: 1px solid #262d3d; }
QMenu { background-color: #151923; color: #e7ecf5; border: 1px solid #262d3d; }
QMenu::item:selected { background-color: #262d3d; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1b2230; color: #e7ecf5; border: 1px solid #262d3d;
    border-radius: 10px; padding: 6px 10px;
}
QTableWidget { background-color: #151923; color: #e7ecf5; border: 1px solid #262d3d; border-radius: 10px; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background-color: #1b2230; color: #8b94a7; border: none; padding: 6px; }
QCheckBox { color: #e7ecf5; }
"""
