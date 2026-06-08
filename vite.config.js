import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "frontend/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        home: "frontend/src/home.jsx",
        thread: "frontend/src/thread.jsx"
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]"
      }
    }
  }
});
