import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://shelldon.monoroc.de',
  output: 'static',

  build: {
    assets: 'assets'
  },

  vite: {
    plugins: [tailwindcss()]
  }
});