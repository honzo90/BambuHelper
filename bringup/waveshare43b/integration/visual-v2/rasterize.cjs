// Local rasterization of approved source assets; no network or image redesign.
// Usage: NODE_PATH=<bundled node_modules> node rasterize.cjs [--browser=/path]
const fs = require('fs');
const path = require('path');
const {chromium} = require('playwright');
const root = __dirname;
const settings = JSON.parse(fs.readFileSync(path.join(root, 'assets.json')));
const browserArg = process.argv.slice(2).find(a => a.startsWith('--browser='));
const browserPath = browserArg ? browserArg.slice(10) : '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
function svgSource(asset) {
  const source = fs.readFileSync(path.join(root, asset.source));
  if (asset.source.endsWith('.svg')) {
    return source.toString().replace(/<svg\b([^>]*)>/, (_match, attributes) =>
      `<svg${attributes.replace(/\s(?:width|height)="[^"]*"/g, '')} width="${asset.width}" height="${asset.height}" preserveAspectRatio="xMidYMid meet">`);
  }
  if (!asset.viewbox || !asset.image_width || !asset.image_height) throw Error('Raster asset needs explicit SVG image geometry');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${asset.width}" height="${asset.height}" viewBox="${asset.viewbox.join(' ')}" preserveAspectRatio="xMidYMid meet"><image href="data:image/png;base64,${source.toString('base64')}" width="${asset.image_width}" height="${asset.image_height}"/></svg>`;
}
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:browserPath, args:['--disable-background-networking']});
  try {
    const page = await browser.newPage({viewport:{width:256,height:256}, deviceScaleFactor:1});
    await page.route(/^https?:\/\//, route => route.abort());
    const records=[];
    for (const asset of settings.assets) {
      if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(asset.name) || asset.width<1 || asset.width>256 || asset.height<1 || asset.height>1024) throw Error('Invalid asset dimensions/name');
      const pixels=await page.evaluate(async ({svg,width,height}) => {
        const image = new Image();
        image.src='data:image/svg+xml;base64,'+btoa(unescape(encodeURIComponent(svg)));
        await image.decode();
        const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
        const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);
        return {png:canvas.toDataURL('image/png').split(',')[1],rgba:Array.from(context.getImageData(0,0,width,height).data)};
      },{svg:svgSource(asset),width:asset.width,height:asset.height});
      fs.mkdirSync(path.join(root,'rasterized'),{recursive:true});
      fs.writeFileSync(path.join(root,'rasterized',asset.name+'.png'),Buffer.from(pixels.png,'base64'));
      fs.writeFileSync(path.join(root,'rasterized',asset.name+'.rgba'),Buffer.from(pixels.rgba));
      records.push({name:asset.name,width:asset.width,height:asset.height});
    }
    fs.writeFileSync(path.join(root,'rasterizer.json'),JSON.stringify({browser:await browser.version(),renderer:'Chromium SVG xMidYMid meet -> Canvas2D sRGB unpremultiplied RGBA',assets:records},null,2)+'\n');
    console.log(JSON.stringify({rasterized:records}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.stack);process.exit(1);});
