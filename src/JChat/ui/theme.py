"""主题 QSS：马卡龙浅色（唯一主题）。"""

QSS = """
* { font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
QMainWindow, QWidget#Root { background-color: #FFF9F0; }
QFrame#Card { background-color: #FFFFFF; border: 1px solid #F4E9DC; border-radius: 24px; }
QLabel { color: #4A3F35; }
QLabel#Muted { color: #9C948A; font-size: 12px; }
QLabel#Title { font-size: 17px; font-weight: 700; color: #4A3F35; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPlainTextEdit#Input {
    background-color: #FFFFFF; color: #4A3F35; border: 2px solid #FFD9E8;
    border-radius: 22px; padding: 10px 16px; font-size: 14px;
}
QPlainTextEdit#Input:focus { border: 2px solid #FFB6C9; }
QLineEdit#HoverInput {
    background-color: #FFFFFF; color: #4A3F35; border: 2px solid #FFD9E8;
    border-radius: 22px; padding: 10px 18px; font-size: 14px;
}
QLineEdit#HoverInput:focus { border: 2px solid #FFB6C9; }
QPushButton#Send {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFB6C9, stop:1 #C9A9FF);
    color: white; border: none; border-radius: 22px; padding: 10px 26px; font-weight: 700;
}
QPushButton#Send:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFA8BF, stop:1 #BD98FF); }
QPushButton#Ghost {
    background: transparent; color: #4A3F35; border: 2px solid #F0E3D4;
    border-radius: 20px; padding: 8px 18px;
}
QPushButton#Ghost:hover { border-color: #FFB6C9; color: #D9709A; }
QPushButton#Danger { background: transparent; color: #E48A8A; border: 2px solid #F5D5D5;
    border-radius: 16px; padding: 6px 14px; }
QPushButton#Danger:hover { background: #FDF0F0; }
QToolTip { background-color: #FFFFFF; color: #4A3F35; border: 1px solid #F0E3D4; }
QMenu { background-color: #FFFFFF; color: #4A3F35; border: 1px solid #F0E3D4;
    border-radius: 14px; padding: 6px; }
QMenu::item { border-radius: 10px; padding: 6px 18px; }
QMenu::item:selected { background-color: #FFF0F5; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF; color: #4A3F35; border: 2px solid #F0E3D4;
    border-radius: 14px; padding: 6px 12px;
}
QTableWidget { background-color: #FFFFFF; color: #4A3F35; border: 1px solid #F0E3D4; border-radius: 14px; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background-color: #FFF6EC; color: #9C948A; border: none; padding: 6px; }
QCheckBox { color: #4A3F35; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #F0D9E4; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""
