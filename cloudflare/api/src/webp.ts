import { Failure } from "./http";

const metadataFlags = 0x08 | 0x04; // VP8X EXIF and XMP bits.

function invalid(): never {
  throw new Failure(503, "The image could not be converted. Please try again later.");
}

type Chunk = { name: string; start: number; end: number; children?: Chunk[] };

function inspect(buffer: ArrayBuffer) {
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const tag = (at: number) => String.fromCharCode(bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]);
  if (
    bytes.length < 12 ||
    tag(0) !== "RIFF" ||
    tag(8) !== "WEBP" ||
    view.getUint32(4, true) !== bytes.length - 8
  )
    invalid();
  let hasMetadata = false;

  function readChunks(begin: number, limit: number, inFrame: boolean): Chunk[] {
    const chunks: Chunk[] = [];
    let hasImage = false;
    for (let start = begin; start < limit;) {
      if (limit - start < 8) invalid();
      const name = tag(start);
      const length = view.getUint32(start + 4, true);
      const end = start + 8 + length + (length % 2);
      if (end > limit || (length % 2 && bytes[end - 1] !== 0)) invalid();
      const chunk: Chunk = { name, start, end };
      if (name === "VP8X") {
        if (inFrame || start !== 12 || length !== 10) invalid();
        if (bytes[start + 8] & metadataFlags) hasMetadata = true;
      } else if (name === "EXIF" || name === "XMP ") {
        hasMetadata = true;
      } else if (name === "ANMF") {
        if (inFrame || length < 16) invalid();
        chunk.children = readChunks(start + 24, start + 8 + length, true);
        hasImage = true;
      } else if (name === "VP8L") {
        if (length < 5 || bytes[start + 8] !== 0x2f || bytes[start + 12] & 0xe0) invalid();
        hasImage = true;
      } else if (name === "VP8 ") {
        if (
          length < 10 ||
          bytes[start + 8] & 1 ||
          bytes[start + 11] !== 0x9d ||
          bytes[start + 12] !== 0x01 ||
          bytes[start + 13] !== 0x2a
        )
          invalid();
        hasImage = true;
      }
      chunks.push(chunk);
      start = end;
    }
    if (!hasImage) invalid();
    return chunks;
  }

  const chunks = readChunks(12, bytes.length, false);
  return { bytes, chunks, hasMetadata };
}

export function webpHasMetadata(buffer: ArrayBuffer) {
  return inspect(buffer).hasMetadata;
}

export function stripWebpMetadata(buffer: ArrayBuffer): ArrayBuffer {
  const { bytes, chunks, hasMetadata } = inspect(buffer);
  if (!hasMetadata) return buffer;
  // Compact in place. All destinations end at or before the source being read.
  const view = new DataView(buffer);
  function compact(entries: Chunk[], position: number): number {
    for (const { name, start, end, children } of entries) {
      if (name === "EXIF" || name === "XMP ") continue;
      if (children) {
        bytes.copyWithin(position, start, start + 24); // Chunk header + 16-byte frame header.
        const next = compact(children, position + 24);
        view.setUint32(position + 4, next - position - 8, true);
        position = next;
      } else {
        bytes.copyWithin(position, start, end);
        if (name === "VP8X") bytes[position + 8] &= ~metadataFlags;
        position += end - start;
      }
    }
    return position;
  }
  const end = compact(chunks, 12);
  view.setUint32(4, end - 8, true);
  return end === bytes.length ? buffer : buffer.slice(0, end);
}
