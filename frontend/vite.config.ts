/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'


// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    // globals: o Testing Library só limpa a tela entre os testes se o afterEach for global
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})

