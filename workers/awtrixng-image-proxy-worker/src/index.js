// AWTRIX NG image proxy: fetch a remote image and return it resized to a
// single 8x8 icon, base64-encoded for the Berry `icon("base64:<data>", x, y)`.
//
// GET /?url=<image url>
//
// The worker owns no state.  Caching is left to the caller: the Berry app
// decides how often to refetch, and the icon itself gets cached by AWTRIX.
//
// Why a worker at all, instead of the AWTRIX fetching the image directly:
// AWTRIX's HTTP client can only pull a small image and play it as-is; it
// cannot resize.  Turning an arbitrary-size remote icon into an 8x8 JPEG is
// pointlessly heavy for the panel, so the resize happens here.

import { decode as decodeJpegLib, encode as encodeJpegLib } from "jpeg-js";
import UPNG from "upng-js";

const SIZE = 8; // AWTRIX icons are 8x8
const BG = [0, 0, 0]; // transparent PNG pixels blend onto the panel's black background before JPEG

const MAX_SOURCE_BYTES = 2 * 1024 * 1024; // don't pull a huge image into the 300 MB Worker slices

export default {
  async fetch(request, env) {
    let out;
    try {
      out = await handle(request);
    } catch (err) {
      out = json(
        { error: "internal", detail: String(err && err.message) },
        500,
      );
    }
    return out;
  },
};

async function handle(request) {
  // Prefer the X-Url header (Berry sends it that way to avoid URL-encoding the
  // target's own query string); ?url= is kept as a plain URL convenience.
  const url = request.headers.get("X-Url") || new URL(request.url).searchParams.get("url");
  if (!url) return json({ error: "missing url" }, 400);

  // Only http(s) — the point is to fetch a remote icon, not a local file.
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return json({ error: "invalid url" }, 400);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return json({ error: "unsupported protocol" }, 400);
  }

  const res = await fetch(url, {
    headers: { "User-Agent": "awtrixng-image-proxy-worker" },
  });
  if (!res.ok) {
    return json(
      { error: "fetch failed", status: res.status, statusText: res.statusText },
      502,
    );
  }
  const contentType = res.headers.get("content-type") || "";
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_SOURCE_BYTES) {
    return json(
      { error: bytes.byteLength === 0 ? "empty body" : "source too large" },
      413,
    );
  }

  console.log("source", {
    url,
    contentType,
    bytes: bytes.byteLength,
  });

  const pixels = decodePixels(bytes, contentType);
  if (!pixels) return json({ error: "unsupported image format" }, 415);

  const rgba = downscale(pixels.data, pixels.width, pixels.height);
  const jpeg = encodeJpegLib(
    { data: rgba, width: SIZE, height: SIZE },
    90,
  ).data; // Uint8Array in the Worker runtime
  const b64 = toBase64(jpeg);
  return json({ data: b64, size: SIZE });
}

// ---------------------------------------------------------------------------
// Decode — jpeg-js and upng-js do the heavy lifting, both pure JS with no
// node builtins so they bundle cleanly for the Worker (see the heatmap worker
// notes on why upng-js over pngjs).
// ---------------------------------------------------------------------------

export function decodePixels(bytes, contentType) {
  const magic = (bytes[0] << 8) | bytes[1];
  if (magic === 0xffd8 || contentType.includes("jpeg") || contentType.includes("jpg")) {
    try {
      const { width, height, data } = decodeJpegLib(bytes, {
        formatAsRGBA: true,
      });
      return { data, width, height };
    } catch (err) {
      console.error("jpeg decode failed", String(err && err.message));
      return null;
    }
  }
  if (
    magic === 0x8950 ||
    contentType.includes("png") ||
    contentType.includes("webp")
  ) {
    try {
      const img = UPNG.decode(bytes);
      const width = img.width;
      const height = img.height;
      const data = new Uint8Array(UPNG.toRGBA8(img)[0]);
      return { data, width, height };
    } catch (err) {
      console.error("png decode failed", String(err && err.message));
      return null;
    }
  }
  return null;
}

// Box-average an arbitrary-size RGBA image down to SIZE x SIZE, blending
// transparent pixels onto the black panel background before discarding alpha
// (JPEG has none).  A source already 8x8 passes through as identity.
export function downscale(src, w, h, outSize = SIZE, bg = BG) {
  const out = new Uint8Array(outSize * outSize * 4);
  for (let y = 0; y < outSize; y++) {
    const y0 = Math.floor((y * h) / outSize);
    const y1 = Math.max(y0 + 1, Math.floor(((y + 1) * h) / outSize));
    for (let x = 0; x < outSize; x++) {
      const x0 = Math.floor((x * w) / outSize);
      const x1 = Math.max(x0 + 1, Math.floor(((x + 1) * w) / outSize));
      let r = 0,
        g = 0,
        b = 0,
        n = 0;
      for (let yy = y0; yy < y1; yy++) {
        for (let xx = x0; xx < x1; xx++) {
          const o = (yy * w + xx) * 4;
          const a = src[o + 3] / 255;
          r += src[o] * a + bg[0] * (1 - a);
          g += src[o + 1] * a + bg[1] * (1 - a);
          b += src[o + 2] * a + bg[2] * (1 - a);
          n++;
        }
      }
      const o = (y * outSize + x) * 4;
      out[o] = Math.round(r / n);
      out[o + 1] = Math.round(g / n);
      out[o + 2] = Math.round(b / n);
      out[o + 3] = 255;
    }
  }
  return out;
}

function toBase64(bytes) {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}