import { resolve } from "node:path";

import { defineConfig } from "vite";

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        solver: resolve(__dirname, "index.html"),
      },
    },
  },
  server: {
    port: 3000,
    open: "index.html",
  },
});
