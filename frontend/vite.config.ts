import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, type UserConfig } from "vite";

interface VitestConfigExport extends UserConfig {
  test?: {
    environment?: string;
    include?: string[];
  };
}

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.spec.ts"]
  }
} as VitestConfigExport);
