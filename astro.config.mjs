import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://shelldon.monoroc.de',
  output: 'static',
  build: {
    assets: 'assets'
  }
});
