# Bundled production font

`Geist-Regular.ttf` is checked into the repository so the Next.js production build does not need to download a font from Google Fonts.

The file was copied from the installed `next@16.2.10` dependency at:

`node_modules/next/dist/compiled/@vercel/og/Geist-Regular.ttf`

If the bundled font is replaced, update `app/layout.tsx`, `app/globals.css`, and the local-font regression test together.
