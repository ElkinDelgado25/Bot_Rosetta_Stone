from dataclasses import dataclass
from typing import Optional

from .role_type import RoleType
from .selector_kind import SelectorKind


@dataclass(frozen=True)
class Selector:
    kind: SelectorKind
    value: Optional[str] = None
    role: Optional[str] = None  # solo para ROLE (button, link, textbox…)
    name: Optional[str] = None  # nombre accesible; si no, usar value por defecto

    # Static factory methods as specified in requirements
    @staticmethod
    def by_label(pattern: str) -> "Selector":
        """Create selector by label text pattern."""
        return Selector(kind=SelectorKind.LABEL, value=pattern)

    @staticmethod
    def by_placeholder(pattern: str) -> "Selector":
        """Create selector by placeholder text pattern."""
        return Selector(kind=SelectorKind.PLACEHOLDER, value=pattern)

    @staticmethod
    def by_text(pattern: str) -> "Selector":
        """Create selector by text content pattern."""
        return Selector(kind=SelectorKind.TEXT, value=pattern)

    @staticmethod
    def by_css(pattern: str) -> "Selector":
        """Create selector by CSS pattern."""
        return Selector(kind=SelectorKind.CSS, value=pattern)

    @staticmethod
    def test_id(test_id: str) -> "Selector":
        """Create selector by test ID."""
        return Selector(kind=SelectorKind.TEST_ID, value=test_id)

    @staticmethod
    def role_button(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.BUTTON,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_link(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.LINK,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_textbox(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.TEXTBOX,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_checkbox(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.CHECKBOX,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_radio(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.RADIO,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_combobox(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.COMBOBOX,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_listbox(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.LISTBOX,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_menuitem(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.MENUITEM,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_tab(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.TAB,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_treeitem(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.TREEITEM,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_heading(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.HEADING,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_image(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.IMAGE,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_table(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.TABLE,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_cell(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.CELL,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_dialog(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.DIALOG,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_alert(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.ALERT,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_progressbar(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.PROGRESSBAR,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_slider(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.SLIDER,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_spinbutton(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.SPINBUTTON,
            name=name_pattern,
            value=name_pattern,
        )

    @staticmethod
    def role_switch(name_pattern: str) -> "Selector":
        return Selector(
            kind=SelectorKind.ROLE,
            role=RoleType.SWITCH,
            name=name_pattern,
            value=name_pattern,
        )
