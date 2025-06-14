import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Remove React plugin since we're using vanilla TypeScript
  plugins: [],
  
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
