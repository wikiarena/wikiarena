import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    // Custom plugin to handle .ts imports in HTML
    {
      name: 'ts-import-resolver',
      configureServer(server) {
        server.middlewares.use('/main.ts', (req, res, next) => {
          // Let Vite handle .ts files naturally
          next();
        });
      }
    }
  ],
  build: {
    rollupOptions: {
      input: 'index.html'
    }
  },
  server: {
    port: 3000,
    open: true
  }
});
