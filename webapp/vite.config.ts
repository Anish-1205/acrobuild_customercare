import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const proxy_paths = [
  "/api",
  "/admin/articles",
  "/admin/knowledge-documents",
  "/admin/users",
  "/ticket",
  "/create_ticket",
  "/customer",
  "/orders",
];

const ignored_watch_paths = [
  "**/.chrome-preview-profile/**",
  "**/.edge-preview-profile/**",
  "**/admin-inbox-preview.png",
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend_url = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
  const proxy = proxy_paths.reduce<Record<string, string>>((entries, path) => {
    entries[path] = backend_url;
    return entries;
  }, {});

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy,
      watch: {
        // Ignore local browser automation profiles to avoid Windows file-lock watch errors.
        ignored: ignored_watch_paths,
      },
    },
  };
});
