import { Failure } from "./http";

type ImageOptions = { width: number; height: number; fit: "scale-down"; metadata: "none" };

export interface ImageBinding {
  info(input: ReadableStream<Uint8Array>): Promise<{ format: string; width?: number; height?: number }>;
  input(input: ReadableStream<Uint8Array>): {
    transform(options: ImageOptions): {
      output(options: {
        format: "image/webp";
        quality: number;
        anim: false;
      }): Promise<{ response(): Response }>;
    };
  };
}

export interface CommunityEnv {
  IMAGES?: ImageBinding;
  PUBLIC_SITE_ORIGIN?: string;
  SUPABASE_URL?: string;
  SUPABASE_PUBLISHABLE_KEY?: string;
  SUPABASE_SECRET_KEY?: string;
  SUPABASE_ANON_KEY?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  TURNSTILE_SITE_KEY?: string;
  TURNSTILE_SECRET_KEY?: string;
  RESEND_API_KEY?: string;
  EMAIL_FROM?: string;
  EMAIL_REPLY_TO?: string;
  NEWSLETTER_TOKEN_SECRET?: string;
}

const inputFormats = new Set(["image/png", "image/jpeg", "image/webp"]);

export async function convertFanArt(file: FormDataEntryValue | null, images?: ImageBinding) {
  if (!file || typeof file === "string" || !inputFormats.has(file.type) || file.size > 3 * 1024 * 1024) {
    throw new Failure(400, "Choose a JPG, PNG or WebP image up to 3 MB.");
  }
  if (!images) throw new Failure(503, "Image processing is temporarily unavailable.");
  const meta = await images.info(file.stream()).catch(() => {
    throw new Failure(400, "This image could not be decoded.");
  });
  const { width, height } = meta;
  if (
    !inputFormats.has(meta.format) ||
    !width ||
    !height ||
    width < 100 ||
    height < 100 ||
    width * height > 12000000
  ) {
    throw new Failure(400, "This image format or size is not supported.");
  }
  const result = await images
    .input(file.stream())
    .transform({ width: 1800, height: 1800, fit: "scale-down", metadata: "none" })
    .output({ format: "image/webp", quality: 88, anim: false })
    .catch(() => {
      throw new Failure(503, "The image could not be converted. Please try again later.");
    });
  const encoded = result.response();
  if (!encoded.ok || encoded.headers.get("Content-Type")?.split(";")[0] !== "image/webp") {
    throw new Failure(503, "The image could not be converted. Please try again later.");
  }
  return await encoded.arrayBuffer();
}
