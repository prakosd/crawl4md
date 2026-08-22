from __future__ import annotations

from app_support.dialog_ui import confirm_dialog_css, scrollable_dialog_css


def test_confirm_dialog_css_scopes_styles_to_given_keys() -> None:
    css = confirm_dialog_css("my_cancel", "my_confirm")
    assert ".st-key-my_cancel button" in css
    assert ".st-key-my_confirm button" in css


def test_confirm_dialog_css_colors_cancel_green_and_confirm_red() -> None:
    css = confirm_dialog_css("cancel_k", "confirm_k")
    # Cancel/keep button is green; confirm button is red.
    assert "#28a745" in css
    assert "#dc3545" in css


def test_confirm_dialog_css_docks_confirm_button_to_the_right() -> None:
    css = confirm_dialog_css("cancel_k", "confirm_k")
    assert "align-items: flex-end;" in css
    assert ".st-key-confirm_k)" in css


def test_scrollable_dialog_css_sizes_dialog_and_scopes_scroll_to_content_key() -> None:
    css = scrollable_dialog_css("my-scope", "my_content", width="60vw", height="55vh")
    # Scope marker + shallow dialog width, and the content container owns the height.
    assert 'class="my-scope"' in css
    assert ":has(.my-scope)" in css
    assert "width: 60vw" in css
    assert "st-key-my_content" in css
    assert "height: 55vh" in css


def test_scrollable_dialog_css_defaults_to_70_percent_viewport() -> None:
    css = scrollable_dialog_css("scope", "content")
    assert "width: 70vw" in css
    assert "height: 70vh" in css
