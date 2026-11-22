import { Failure } from "./http";
import type { CommunityEnv } from "./images";

export function mailConfigured(env: CommunityEnv) {
  return Boolean(env.RESEND_API_KEY && env.EMAIL_FROM);
}

export function localizedCommunityUrl(env: CommunityEnv, language: string, path: string) {
  const origin = env.PUBLIC_SITE_ORIGIN || "https://hyruleatlas.com";
  return origin + (language === "en" ? "" : "/" + language) + path;
}

function configuredReplyTo(env: CommunityEnv) {
  const value = env.EMAIL_REPLY_TO?.trim();
  if (!value) return undefined;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
    throw new Failure(503, "Email replies are not configured.");
  return value;
}
export async function sendCommunityMail(
  env: CommunityEnv,
  to: string,
  subject: string,
  content: string,
  unsubscribe?: string,
  idempotency?: string,
  language = "en",
) {
  if (!mailConfigured(env)) throw new Failure(503, "Email registration is not open yet.");
  const plain = content
    .replace(/<a[^>]+href="([^"]+)"[^>]*>(.*?)<\/a>/g, "$2 ($1)")
    .replace(/<\/(p|h2|li)>/g, "\n\n")
    .replace(/<br\s*\/?>/g, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  const replyTo = configuredReplyTo(env),
    forum = localizedCommunityUrl(env, language, "/forum"),
    privacy = localizedCommunityUrl(env, language, "/privacy");
  const privateContactLabel: Record<string, string> = {
    en: "Privacy & private contact",
    fr: "Confidentialité et demande privée",
    es: "Privacidad y contacto privado",
    ja: "プライバシーと非公開のお問い合わせ",
    zh: "隐私与私密联系",
  };
  const contactLabel = privateContactLabel[language] || privateContactLabel.en;
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    redirect: "manual",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
      "User-Agent": "hyrule-atlas/1.0",
      ...(idempotency ? { "Idempotency-Key": idempotency } : {}),
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [to],
      subject,
      text: `Hyrule Atlas\n\n${plain}\n\nForum: ${forum}\n${contactLabel}: ${privacy}`,
      html: `<div style="font-family:Georgia,serif;max-width:600px;margin:auto;line-height:1.7;color:#16352e"><h1>Hyrule Atlas</h1>${content}<hr><p>Hyrule Atlas · Independent fan community · <a href="${forum}">Forum</a> · <a href="${privacy}">${contactLabel}</a></p></div>`,
      ...(replyTo ? { reply_to: replyTo } : {}),
      ...(unsubscribe
        ? {
            headers: {
              "List-Unsubscribe": `<${unsubscribe}>`,
              "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
          }
        : {}),
    }),
    signal: AbortSignal.timeout(12000),
  });
  if (!r.ok) throw new Failure(503, "The email could not be sent. Please try again later.");
  const result: any = await r.json().catch(() => null);
  if (typeof result?.id !== "string" || !result.id.trim())
    throw new Failure(503, "The email provider did not confirm this message.");
  return { id: result.id as string, status: r.status };
}
