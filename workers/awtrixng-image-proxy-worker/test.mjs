// Offline tests for the pure computation functions.  Run with `node test.mjs`
// (after `npm install` — the decoders bring jpeg-js and upng-js).
//
// Imports directly from src/index.js — no drift risk.
//
// What is NOT covered here (needs a live URL + wrangler dev):
//   - The remote fetch, size limit and SSRF-adjacent checks
//   - End-to-end base64 icon that AWTRIX would actually render

import UPNG from "upng-js";

const mod = await import(new URL("./src/index.js", import.meta.url));
const { decodePixels, downscale } = mod;
const SIZE = 8;
const BG = [0, 0, 0];

let failed = 0;
function eq(name, got, want) {
  if (String(got) !== String(want)) {
    failed++;
    console.log(`  FAIL ${name}: got ${got}, want ${want}`);
  } else {
    console.log(`  ok   ${name}`);
  }
}
function near(name, got, want, tol) {
  const ok = Math.abs(got - want) <= tol;
  if (!ok) {
    failed++;
    console.log(`  FAIL ${name}: got ${got}, want ${want}±${tol}`);
  } else {
    console.log(`  ok   ${name}`);
  }
}

// --- decodePixels: unsupported format is rejected ---------------------------

console.log("decodePixels");
{
  const bad = new Uint8Array([0x00, 0x01, 0x02, 0x03]);
  eq("garbage is null", decodePixels(bad, ""), null);
  eq("no bytes is null", decodePixels(new Uint8Array(0), ""), null);
}

// --- decodePixels: PNG decode + box-average downscale to 8x8 ---------------

console.log("png scale");
{
  // 16x16 PNG: left half opaque red, right half opaque green.
  const w = 16,
    h = 16;
  const rgba = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = (y * w + x) * 4;
      if (x < w / 2) rgba[o] = 255;
      else rgba[o + 1] = 255;
      rgba[o + 3] = 255;
    }
  }
  const png = new Uint8Array(UPNG.encode([rgba], w, h, 0, null, true));
  const img = decodePixels(png, "image/png");
  eq("png decodes", img !== null, true);
  eq("png dims", `${img.width}x${img.height}`, "16x16");
  const out = downscale(img.data, img.width, img.height);
  eq("out is 8x8 rgba", out.length, 8 * 8 * 4);
  const row0 = out.slice(0, 8 * 4);
  const expected = [];
  for (let x = 0; x < 8; x++)
    expected.push(...(x < 4 ? [255, 0, 0, 255] : [0, 255, 0, 255]));
  eq("left half red", String(row0), String(expected));
  // Every row the same (uniform image).
  eq("all rows uniform", String(out.slice(8 * 4, 16 * 4)), String(row0));
}

// --- alpha blend: transparent pixels fall back to the black panel background ---

console.log("alpha blend");
{
  const w = 8,
    h = 8;
  const rgba = new Uint8Array(w * h * 4);
  // left transparent, right opaque red
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = (y * w + x) * 4;
      if (x < 4) {
        rgba[o] = 255;
        rgba[o + 3] = 0;
      } else {
        rgba[o] = 255;
        rgba[o + 3] = 255;
      }
    }
  }
  const out = downscale(rgba, w, h);
  // transparent pixel at (0,0) already 8x8 → identity, so it blends to BG
  near("transparent -> black", out[0], BG[0], 0);
  near("transparent -> black g", out[1], BG[1], 0);
  const o = 4 * 4; // (4,0) opaque red
  eq("opaque keeps color", String([out[o], out[o + 1], out[o + 2]]), "255,0,0");
}

console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);