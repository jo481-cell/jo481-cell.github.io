export class Failure extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export class ApiResponse {
  private code = 200;
  private headers = new Headers({
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
  });

  setHeader(name: string, value: string | string[]) {
    this.headers.delete(name);
    for (const item of Array.isArray(value) ? value : [value]) {
      this.headers.append(name, item);
    }
  }

  status(code: number) {
    this.code = code;
    return this;
  }

  json(data: unknown) {
    return Response.json(data, { status: this.code, headers: this.headers });
  }

  send(body: BodyInit | null) {
    return new Response(body, { status: this.code, headers: this.headers });
  }

  redirect(status: number, url: string) {
    this.setHeader("Location", url);
    return this.status(status).send(null);
  }
}

export function cookies(request: Request): Record<string, string> {
  const result: Record<string, string> = Object.create(null);
  for (const value of (request.headers.get("Cookie") || "").split(";")) {
    const separator = value.indexOf("=");
    if (separator < 0) continue;
    const name = value.slice(0, separator).trim();
    if (name !== "ha_access" && name !== "ha_refresh") continue;
    try {
      result[name] = decodeURIComponent(value.slice(separator + 1));
    } catch {
      // A malformed cookie provides no session; a separate refresh cookie can still work.
    }
  }
  return result;
}

async function readLimited(request: Request, maxSize: number) {
  const failure = () => new Failure(413, "This request is too large.");
  if (Number(request.headers.get("Content-Length")) > maxSize) throw failure();
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxSize) {
        await reader.cancel();
        throw failure();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

export async function input(request: Request) {
  const bytes = await readLimited(request, 50000);
  try {
    const data = JSON.parse(new TextDecoder().decode(bytes) || "{}");
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error();
    return data;
  } catch {
    throw new Failure(400, "Invalid request.");
  }
}

export async function multipart(request: Request) {
  const bytes = await readLimited(request, 4300000);
  try {
    return await new Response(bytes, {
      headers: { "Content-Type": request.headers.get("Content-Type") || "" },
    }).formData();
  } catch {
    throw new Failure(400, "Please choose a valid upload.");
  }
}
