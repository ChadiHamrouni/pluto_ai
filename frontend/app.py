"""Personal AI Assistant — DearPyGui frontend."""
from __future__ import annotations

import threading

import dearpygui.dearpygui as dpg

from api import client

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = (8,   8,  12, 255)
PANEL       = (14,  14,  20, 255)
PANEL_LIGHT = (20,  20,  30, 255)
NEON        = (0,  200, 255, 255)      # cyan neon accent
NEON_DIM    = (0,  200, 255,  60)
NEON_GLOW   = (0,  160, 220, 180)
USER_BUBBLE = (18,  18,  28, 255)
AI_BUBBLE   = (10,  10,  18, 255)
TEXT_WHITE  = (230, 230, 240, 255)
TEXT_DIM    = (120, 120, 140, 255)
TEXT_NEON   = (0,  210, 255, 255)
RED_ERR     = (255,  70,  70, 255)
GREEN_OK    = ( 50, 220, 120, 255)

# chat history stored as list of {"role": ..., "content": ...}
_history: list[dict] = []
_thinking = False


# ── Theme ─────────────────────────────────────────────────────────────────────
def _apply_global_theme():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,        BG,          category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,         PANEL,       category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,         PANEL,       category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,         PANEL_LIGHT, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,  (30, 30, 45, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,   (35, 35, 55, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Button,          (0, 160, 210, 200), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,   NEON,        category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,    (0, 140, 190, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text,            TEXT_WHITE,  category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border,          NEON_DIM,    category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow,    (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,     BG,          category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,   NEON_DIM,    category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, NEON_GLOW, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,         PANEL,       category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,   PANEL,       category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_MenuBarBg,       PANEL,       category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Header,          NEON_DIM,    category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,   (0, 200, 255, 80), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Separator,       NEON_DIM,    category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,   10, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,     6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,     8, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   16, 16, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    12,  8, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     10,  8, category=dpg.mvThemeCat_Core)
    dpg.bind_theme(global_theme)


def _neon_button_theme():
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (0, 180, 230, 220), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, NEON,               category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (0, 140, 190, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (8, 8, 12, 255),    category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6, category=dpg.mvThemeCat_Core)
    return t


def _input_theme():
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (18, 18, 28, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (24, 24, 36, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (28, 28, 42, 255), category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Border,         NEON_GLOW,         category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(dpg.mvThemeCol_Text,           TEXT_WHITE,        category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,  6, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,  12, 10, category=dpg.mvThemeCat_Core)
    return t


# ── Chat bubble rendering ─────────────────────────────────────────────────────
def _render_message(role: str, content: str):
    is_user = role == "user"
    label   = "You" if is_user else "AI"
    color   = TEXT_NEON if not is_user else TEXT_DIM

    with dpg.group(parent="chat_scroll"):
        dpg.add_spacer(height=4)
        dpg.add_text(label, color=color)
        with dpg.child_window(
            autosize_x=True,
            auto_resize_y=True,
            border=True,
            parent="chat_scroll",
        ):
            dpg.add_text(
                content,
                wrap=0,
                color=TEXT_WHITE if not is_user else (200, 200, 215, 255),
            )
        dpg.add_spacer(height=2)


def _render_all_messages():
    dpg.delete_item("chat_scroll", children_only=True)
    for msg in _history:
        _render_message(msg["role"], msg["content"])
    # scroll to bottom
    dpg.set_y_scroll("chat_scroll", dpg.get_y_scroll_max("chat_scroll") + 9999)


# ── Send logic (runs in thread) ───────────────────────────────────────────────
def _do_send(message: str):
    global _thinking
    try:
        response = client.send_message(message, _history[:-1])  # exclude the user msg we just added
        _history.append({"role": "assistant", "content": response})
    except PermissionError:
        _history.append({"role": "assistant", "content": "⚠ Session expired. Please log in again."})
        dpg.show_item("login_window")
        dpg.hide_item("chat_window")
    except Exception as exc:
        _history.append({"role": "assistant", "content": f"⚠ Error: {exc}"})
    finally:
        _thinking = False
        dpg.set_value("status_text", "")
        dpg.enable_item("send_btn")
        dpg.enable_item("msg_input")
        _render_all_messages()


def _on_send():
    global _thinking
    if _thinking:
        return
    message = dpg.get_value("msg_input").strip()
    if not message:
        return

    dpg.set_value("msg_input", "")
    _history.append({"role": "user", "content": message})
    _render_all_messages()

    _thinking = True
    dpg.disable_item("send_btn")
    dpg.disable_item("msg_input")
    dpg.set_value("status_text", "Thinking...")

    threading.Thread(target=_do_send, args=(message,), daemon=True).start()


def _on_input_enter(sender, app_data):
    # Enter key in multiline = submit; Shift+Enter = newline (DPG default)
    if dpg.is_key_down(dpg.mvKey_Return) and not dpg.is_key_down(dpg.mvKey_LShift):
        _on_send()


# ── Login logic ───────────────────────────────────────────────────────────────
def _on_login():
    username = dpg.get_value("username_input").strip()
    password = dpg.get_value("password_input").strip()
    dpg.set_value("login_error", "")

    try:
        ok = client.login(username, password)
    except ConnectionError as e:
        dpg.set_value("login_error", str(e))
        return

    if ok:
        dpg.hide_item("login_window")
        dpg.show_item("chat_window")
        dpg.focus_item("msg_input")
    else:
        dpg.set_value("login_error", "Invalid username or password.")


def _on_logout():
    global _history
    client.logout()
    _history = []
    dpg.delete_item("chat_scroll", children_only=True)
    dpg.set_value("username_input", "")
    dpg.set_value("password_input", "")
    dpg.set_value("login_error", "")
    dpg.hide_item("chat_window")
    dpg.show_item("login_window")


# ── Windows ───────────────────────────────────────────────────────────────────
def _build_login_window(W: int, H: int):
    with dpg.window(
        tag="login_window",
        label="",
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        no_scrollbar=True,
        pos=(0, 0),
        width=W,
        height=H,
    ):
        # vertical centering
        dpg.add_spacer(height=H // 3)

        with dpg.group(horizontal=False):
            # title
            dpg.add_text("PERSONAL AI", color=NEON)
            dpg.add_spacer(height=2)
            dpg.add_text("Sign in to continue", color=TEXT_DIM)
            dpg.add_spacer(height=24)

            dpg.add_text("Username", color=TEXT_DIM)
            dpg.add_input_text(tag="username_input", width=340, hint="admin")
            dpg.bind_item_theme("username_input", _input_theme())
            dpg.add_spacer(height=10)

            dpg.add_text("Password", color=TEXT_DIM)
            dpg.add_input_text(tag="password_input", width=340, password=True, hint="••••••••",
                               on_enter=True, callback=_on_login)
            dpg.bind_item_theme("password_input", _input_theme())
            dpg.add_spacer(height=16)

            btn = dpg.add_button(label="Sign In", width=340, height=40, callback=_on_login)
            dpg.bind_item_theme(btn, _neon_button_theme())
            dpg.add_spacer(height=10)

            dpg.add_text("", tag="login_error", color=RED_ERR)

        # center the group
        dpg.set_item_pos(dpg.last_container_root_child(), ((W - 340) // 2, H // 3))


def _build_chat_window(W: int, H: int):
    HEADER_H  = 52
    FOOTER_H  = 80
    SIDEBAR_W = 0   # no sidebar for now — clean single-pane layout

    with dpg.window(
        tag="chat_window",
        label="",
        no_title_bar=True,
        no_resize=True,
        no_move=True,
        no_scrollbar=True,
        pos=(0, 0),
        width=W,
        height=H,
        show=False,
    ):
        # ── Header bar ──
        with dpg.child_window(height=HEADER_H, border=False, tag="header_bar"):
            with dpg.group(horizontal=True):
                dpg.add_text("PERSONAL AI", color=NEON)
                dpg.add_spacer(width=12)
                dpg.add_text("assistant", color=TEXT_DIM)
                # push logout to right
                dpg.add_spacer(width=W - 340)
                logout_btn = dpg.add_button(label="Log out", callback=_on_logout, width=90, height=30)
                dpg.bind_item_theme(logout_btn, _neon_button_theme())

        dpg.add_separator()

        # ── Chat scroll area ──
        chat_h = H - HEADER_H - FOOTER_H - 28
        dpg.add_child_window(
            tag="chat_scroll",
            height=chat_h,
            border=False,
            autosize_x=True,
        )

        dpg.add_separator()
        dpg.add_spacer(height=6)

        # ── Footer input ──
        with dpg.group(horizontal=True):
            dpg.add_input_text(
                tag="msg_input",
                width=W - 140,
                height=44,
                multiline=False,
                hint="Message your AI assistant…",
                on_enter=True,
                callback=_on_send,
            )
            dpg.bind_item_theme("msg_input", _input_theme())

            send_btn = dpg.add_button(
                label="Send",
                tag="send_btn",
                width=100,
                height=44,
                callback=_on_send,
            )
            dpg.bind_item_theme(send_btn, _neon_button_theme())

        dpg.add_spacer(height=4)
        dpg.add_text("", tag="status_text", color=TEXT_NEON)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    dpg.create_context()
    _apply_global_theme()

    W, H = 1100, 720

    dpg.create_viewport(
        title="Personal AI Assistant",
        width=W,
        height=H,
        min_width=800,
        min_height=500,
        clear_color=BG,
    )

    _build_login_window(W, H)
    _build_chat_window(W, H)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("login_window", True)

    while dpg.is_dearpygui_running():
        # keep primary window filling the viewport on resize
        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()

        for win in ("login_window", "chat_window"):
            if dpg.does_item_exist(win):
                dpg.set_item_width(win, vw)
                dpg.set_item_height(win, vh)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    main()