const { before, test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { buildSync } = require("esbuild");

// Lossless libwebp fixtures. Both have alpha, ICC, EXIF and XMP. The animation
// has two differently coloured frames, two loops, and distinct frame durations.
const still =
  "UklGRnQAAABXRUJQVlA4WAoAAAA8AAAABAAAAwAASUNDUAgAAABJQ0MtdGVzdFZQOEwPAAAALwTAABAHEP2PAgYiov8BAEVYSUYHAAAAZml4dHVyZQBYTVAgHQAAADx4OnhtcG1ldGE+c2FtcGxlPC94OnhtcG1ldGE+AA==";
const animated =
  "UklGRtAAAABXRUJQVlA4WAoAAAA+AAAABAAAAwAASUNDUAgAAABJQ0MtdGVzdEFOSU0GAAAAAAAAAAIAQU5NRigAAAAAAAAAAAAEAAADAABkAAACVlA4TA8AAAAvBMAAEAcQ/Y8CBiKi/wEAQU5NRigAAAAAAAAAAAAEAAADAACWAAACVlA4TA8AAAAvBMAAEAcQ0f8CBSKi/wEARVhJRg0AAABFeGlmAABmaXh0dXJlAFhNUCAdAAAAPHg6eG1wbWV0YT5zYW1wbGU8L3g6eG1wbWV0YT4A";

let strip, hasMetadata, convert;
before(async () => {
  const module = buildSync({
    stdin: {
      resolveDir: path.join(__dirname, "../src"),
      contents: 'export * from "./webp"; export { convertFanArt } from "./images";',
    },
    bundle: true,
    format: "esm",
    write: false,
  }).outputFiles[0].contents;
  ({
    stripWebpMetadata: strip,
    webpHasMetadata: hasMetadata,
    convertFanArt: convert,
  } = await import("data:text/javascript;base64," + Buffer.from(module).toString("base64")));
});
const owned = (bytes) => Uint8Array.from(bytes).buffer;
function split(buf, start = 12) {
  const outs = [];
  while (start < buf.length) {
    const name = buf.toString("ascii", start, start + 4);
    const n = buf.readUInt32LE(start + 4);
    outs.push({ name, payload: buf.subarray(start + 8, start + 8 + n) });
    start += 8 + n + (n % 2);
  }
  assert.equal(start, buf.length);
  return outs;
}
function chunk(name, payload) {
  const out = Buffer.alloc(8 + payload.length + (payload.length % 2));
  out.write(name, 0, 4, "ascii");
  out.writeUInt32LE(payload.length, 4);
  payload.copy(out, 8);
  return out;
}
function riff(entries) {
  const out = Buffer.concat([
    Buffer.from("RIFF0000WEBP"),
    ...entries.map(({ name, payload }) => chunk(name, payload)),
  ]);
  out.writeUInt32LE(out.length - 8, 4);
  return out;
}

for (const [label, encoded, flags] of [
  ["still", still, 0x30],
  ["animation", animated, 0x32],
]) {
  test(label + " drops real metadata chunks but preserves signalling and image bytes", () => {
    const original = Buffer.from(encoded, "base64");
    const before = split(original);
    const result = Buffer.from(strip(owned(original)));
    assert.equal(result.readUInt32LE(4), result.length - 8);
    assert.equal(hasMetadata(owned(result)), false);
    const after = split(result);
    const expected = before.filter(({ name }) => !["EXIF", "XMP "].includes(name));
    assert.deepEqual(
      after.map((c) => c.name),
      expected.map((c) => c.name),
    );
    assert.equal(after[0].payload[0], flags);
    assert.deepEqual(after[0].payload.subarray(1), expected[0].payload.subarray(1));
    assert.deepEqual(after.slice(1), expected.slice(1)); // Includes encoded pixels, ICC, loop, timings and alpha.
    const clean = owned(result);
    assert.equal(strip(clean), clean);
  });
}

test("removes frame-local metadata, updates ANMF lengths, preserves opaque bytes, and clears stale flags", () => {
  const parts = split(Buffer.from(animated, "base64")).filter((c) => !["EXIF", "XMP "].includes(c.name));
  const pos = parts.findIndex((c) => c.name === "ANMF");
  const before = parts[pos].payload;
  const opaque = chunk("test", Buffer.from("A string EXIF XMP inside an unrelated chunk"));
  parts[pos].payload = Buffer.concat([
    before.subarray(0, 16),
    chunk("EXIF", Buffer.from([1, 2, 3])),
    before.subarray(16),
    chunk("XMP ", Buffer.from([4])),
    opaque,
  ]);
  const result = Buffer.from(strip(owned(riff(parts))));
  const kept = split(result);
  assert.equal(kept[0].payload[0], 0x32);
  assert.deepEqual(kept[pos].payload, Buffer.concat([before, opaque]));
  assert.deepEqual(kept[pos + 1], parts[pos + 1]);
  assert.equal(hasMetadata(owned(result)), false);
  const flagsOnly = Buffer.from(result);
  flagsOnly[20] |= 0x0c;
  assert.deepEqual(Buffer.from(strip(owned(flagsOnly))), result);
  const noFlags = Buffer.from(still, "base64");
  noFlags[20] &= ~0x0c;
  assert.equal(hasMetadata(owned(noFlags)), true);
  assert.equal(
    split(Buffer.from(strip(owned(noFlags)))).some((c) => c.name === "EXIF" || c.name === "XMP "),
    false,
  );
});

test("malformed RIFF, VP8X and frame bounds are rejected before upload", () => {
  const original = Buffer.from(still, "base64");
  const tinyHeader = Buffer.from("RIFF");
  const wrongFormat = Buffer.from(original);
  wrongFormat.write("JUNK", 8);
  const badChunk = Buffer.from(original);
  badChunk.writeUInt32LE(0xffffffff, 16);
  const invalid = [
    tinyHeader,
    wrongFormat,
    badChunk,
    original.subarray(0, original.length - 1),
    riff([{ name: "EXIF", payload: Buffer.alloc(0) }]),
    riff([{ name: "VP8L", payload: Buffer.alloc(6) }]),
    riff([{ name: "VP8 ", payload: Buffer.alloc(10) }]),
    riff([
      { name: "VP8X", payload: Buffer.alloc(6) },
      { name: "VP8L", payload: Buffer.alloc(9) },
    ]),
    riff([{ name: "ANMF", payload: Buffer.alloc(8) }]),
    riff([{ name: "ANMF", payload: Buffer.concat([Buffer.alloc(16), Buffer.from("broken")]) }]),
  ];
  const xmp = Buffer.from(original);
  xmp[xmp.length - 1] = 1; // Non-zero padding after odd XMP payload.
  invalid.push(xmp);
  for (const bytes of invalid)
    assert.throws(
      () => strip(owned(bytes)),
      (e) => e.status === 503,
    );
});

test("the upload conversion sanitizes even if the hosted encoder retains metadata, and rejects damaged output", async () => {
  let upstream = Buffer.from(still, "base64");
  const host = {
    info: async () => ({ format: "image/jpeg", width: 150, height: 110 }),
    input: () => ({
      transform: () => ({
        output: async () => ({
          response: () => new Response(upstream, { headers: { "Content-Type": "image/webp" } }),
        }),
      }),
    }),
  };
  const file = new File([new Uint8Array([0xff, 0xd8])], "test.jpg", { type: "image/jpeg" });
  assert.equal(hasMetadata(owned(upstream)), true);
  const cleaned = await convert(file, host);
  assert.equal(hasMetadata(cleaned), false);
  assert.deepEqual(Buffer.from(cleaned), Buffer.from(strip(owned(upstream))));
  upstream = upstream.subarray(0, upstream.length - 1);
  await assert.rejects(convert(file, host), (e) => e.status === 503);
  upstream = riff([
    ...split(Buffer.from(still, "base64")),
    { name: "JUNK", payload: Buffer.alloc(3 * 1024 * 1024) },
  ]);
  await assert.rejects(convert(file, host), (e) => e.status === 400 && /too large/.test(e.message));
});
