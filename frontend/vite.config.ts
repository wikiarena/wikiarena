import { resolve } from "node:path";

import { defineConfig } from "vite";

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        home: resolve(__dirname, "index.html"),
        leaderboard: resolve(__dirname, "leaderboard.html"),
        race: resolve(__dirname, "race.html"),
        solver: resolve(__dirname, "solver.html"),
      },
    },
  },
  server: {
    port: 3000,
    open: "index.html",
  },
});
