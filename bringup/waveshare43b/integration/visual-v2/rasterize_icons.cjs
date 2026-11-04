// Rasterize only the four editable dashboard SVGs using local sharp/librsvg.
// No browser, network requests, atlas changes or runtime image processing.
// Usage: NODE_PATH=<node_modules containing sharp> node rasterize_icons.cjs
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const root = __dirname;
const names = new Set(['Nozzle', 'Bed', 'Chamber', 'Spool']);

(async () => {
  const settings = JSON.parse(fs.readFileSync(path.join(root, 'assets.json')));
  const assets = settings.assets.filter(asset => names.has(asset.name));
  if (assets.length !== names.size) throw Error('Missing dashboard icon');
  const metadataPath = path.join(root, 'rasterizer.json');
  const metadata = JSON.parse(fs.readFileSync(metadataPath));
  // Preserve the original renderer provenance for unchanged assets.
  for (const record of metadata.assets) {
    if (!record.renderer) {
      record.renderer = metadata.renderer;
      record.browser = metadata.browser;
    }
  }
  for (const asset of assets) {
    if (!asset.source.endsWith('.svg') || asset.width < 1 || asset.width > 256 ||
        asset.height < 1 || asset.height > 1024) throw Error('Invalid SVG icon');
    const source = fs.readFileSync(path.join(root, asset.source), 'utf8');
    // The canvas size is part of the sprite contract; preserve the viewBox.
    const svg = source.replace(/<svg\b([^>]*)>/, (_match, attrs) =>
      `<svg${attrs.replace(/\s(?:width|height)="[^"]*"/g, '')} width="${asset.width}" height="${asset.height}" preserveAspectRatio="xMidYMid meet">`);
    const {data, info} = await sharp(Buffer.from(svg)).ensureAlpha()
      .raw().toBuffer({resolveWithObject: true});
    if (info.width !== asset.width || info.height !== asset.height || info.channels !== 4)
      throw Error('Unexpected RGBA geometry');
    const target = path.join(root, 'rasterized', asset.name);
    fs.writeFileSync(target + '.rgba', data);
    await sharp(data, {raw: info}).png().toFile(target + '.png');
    const record = metadata.assets.find(record => record.name === asset.name);
    if (!record) throw Error('Missing raster provenance record');
    delete record.browser;
    Object.assign(record, {renderer: 'librsvg SVG xMidYMid meet -> sRGB straight RGBA',
      sharp: sharp.versions.sharp, librsvg: sharp.versions.rsvg});
  }
  metadata.renderer = 'Per-asset renderers; unchanged artwork retains original Chromium raster';
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2) + '\n');
  console.log(JSON.stringify({rasterized: assets.map(asset => asset.name)}));
})().catch(error => { console.error(error); process.exit(1); });
