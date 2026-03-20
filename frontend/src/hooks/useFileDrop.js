import { useEffect } from "react";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { readFile } from "@tauri-apps/plugin-fs";

const IMAGE_EXTS  = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp"]);
const SUPPORTED   = new Set([...IMAGE_EXTS, "pdf", "txt"]);
const MIME_MAP    = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
  webp: "image/webp", gif: "image/gif",  bmp: "image/bmp",
  pdf: "application/pdf", txt: "text/plain",
};

/**
 * Listens for Tauri file-drop events and calls:
 *   onDragging(bool)   — when a file is hovered / leaves
 *   onFile(attachment) — when a valid file is dropped
 *   onError(msg)       — when an unsupported or unreadable file is dropped
 */
export function useFileDrop({ onDragging, onFile, onError }) {
  useEffect(() => {
    let unlisten;

    const setup = async () => {
      unlisten = await getCurrentWebview().onDragDropEvent(async (event) => {
        const { type } = event.payload;

        if (type === "over") {
          onDragging(true);
        } else if (type === "cancelled") {
          onDragging(false);
        } else if (type === "drop") {
          onDragging(false);
          const paths = event.payload.paths;
          if (!paths?.length) return;

          const filePath = paths[0];
          const ext      = filePath.split(".").pop().toLowerCase();

          if (!SUPPORTED.has(ext)) {
            onError("Supported files: images, PDFs, and .txt files.");
            return;
          }

          try {
            const bytes    = await readFile(filePath);
            const mime     = MIME_MAP[ext] || "application/octet-stream";
            const blob     = new Blob([bytes], { type: mime });
            const fileName = filePath.split(/[\\/]/).pop();
            const file     = new File([blob], fileName, { type: mime });
            const isImage  = IMAGE_EXTS.has(ext);
            const preview  = isImage ? URL.createObjectURL(blob) : null;

            onFile({ file, preview, isPdf: !isImage, fileExt: ext });
          } catch (e) {
            onError("Failed to read file: " + e.message);
          }
        }
      });
    };

    setup();
    return () => { unlisten?.(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
