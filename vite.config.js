import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
var proxy_paths = [
    "/api",
    "/auth",
    "/admin/articles",
    "/admin/knowledge-documents",
    "/admin/users",
    "/ticket",
    "/create_ticket",
    "/customer",
    "/orders",
];
var ignored_watch_paths = [
    "**/.chrome-preview-profile/**",
    "**/.edge-preview-profile/**",
    "**/admin-inbox-preview.png",
];
export default defineConfig(function (_a) {
    var mode = _a.mode;
    var env = loadEnv(mode, ".", "");
    var backend_url = env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
    var proxy = proxy_paths.reduce(function (entries, path) {
        entries[path] = backend_url;
        return entries;
    }, {});
    return {
        plugins: [react()],
        test: {
            environment: "jsdom",
        },
        server: {
            port: 5173,
            proxy: proxy,
            watch: {
                // Ignore local browser automation profiles to avoid Windows file-lock watch errors.
                ignored: ignored_watch_paths,
            },
        },
    };
});
