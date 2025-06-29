import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss()],
  
  // Ensure proper handling of TypeScript modules
  esbuild: {
    target: 'es2020'
  },
  
  // Development server config
  server: {
    port: 3000,
    host: true
  },
  
  // Build config
  build: {
    target: 'es2020',
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      input: 'game.html'
    }
  }
})
