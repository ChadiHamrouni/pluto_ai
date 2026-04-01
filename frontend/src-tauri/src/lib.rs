use tauri::Manager;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let ctrl_space = Shortcut::new(Some(Modifiers::CONTROL), Code::Space);
    let ctrl_m = Shortcut::new(Some(Modifiers::CONTROL), Code::KeyM);

    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(move |app| {
            let handle = app.handle().clone();
            app.global_shortcut().on_shortcut(ctrl_space, move |_app, _shortcut, event| {
                if event.state == ShortcutState::Pressed {
                    if let Some(win) = handle.get_webview_window("main") {
                        let visible = win.is_visible().unwrap_or(false);
                        if visible {
                            let _ = win.hide();
                        } else {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                }
            })?;

            let handle2 = app.handle().clone();
            app.global_shortcut().on_shortcut(ctrl_m, move |_app, _shortcut, event| {
                if event.state == ShortcutState::Pressed {
                    if let Some(win) = handle2.get_webview_window("main") {
                        let is_minimized = win.is_minimized().unwrap_or(false);
                        let is_focused = win.is_focused().unwrap_or(false);
                        let is_maximized = win.is_maximized().unwrap_or(false);

                        if is_minimized || !is_focused {
                            let _ = win.unminimize();
                            let _ = win.show();
                            let _ = win.set_focus();
                        } else if !is_maximized {
                            let _ = win.maximize();
                        } else {
                            let _ = win.minimize();
                        }
                    }
                }
            })?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}