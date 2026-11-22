const { before, after, test } = require("node:test");
const assert = require("node:assert/strict");
const { build } = require("esbuild");
const { Miniflare, convertV4MiniflareOptions } = require("miniflare");
const path = require("node:path");
const { createHmac } = require("node:crypto");

const site = "https://atlas.example";
const database = "https://database.example";
const userId = "11111111-1111-4111-8111-111111111111";
const newsletterSecret = "local-test-only-signing-secret-for-a-mock";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAH0AAABkCAIAAAAkO6ghAAAA9klEQVR4nO3SMQ0AIAADQUAKK+bwP+GCX+4MNPl0nrsH363/k+ie8feG7g3dG7o3dG/o3tC9oXtD94buDd0bujd0b+je0L2he0P3hu4N3Ru6N3Rv6N7QvaF7Q/eG7g3dG7o3dG/o3tC9oXtD94buDd0bujd0b+je0L2he0P3hu4N3Ru6N3Rv6N7QvaF7Q/eG7g3dG7o3dG/o3tC9oXtD94buDd0bujd0b+je0L2he0P3hu4N3Ru6N3Rv6N7QvaF7Q/eG7g3dG7o3dG/o3tC9oXtD94buDd0bujd0b+je0L2he0P3hu4N3Ru6N3Rv6N7QvaF7Q/eReGoJAYWc4NkSAAAAAElFTkSuQmCC",
  "base64",
);
let runtime;
let calls;
let stored;
let artRows;
let registered;
let accountDeleted;

function reply(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function upstream(req) {
  const url = new URL(req.url);
  calls.push([req.method, url.pathname]);
  if (url.hostname === "challenges.cloudflare.com")
    return reply({ success: true, action: "login", hostname: "atlas.example" });
  assert.equal(url.origin, database);
  if (url.pathname === "/auth/v1/token")
    return reply({
      user: { id: userId, email_confirmed_at: "2026-11-01" },
      access_token: "session-value",
      refresh_token: "refresh-value",
      expires_in: 3600,
    });
  if (url.pathname === "/auth/v1/user")
    return reply({ id: userId, email: "member@example.invalid", email_confirmed_at: "2026-11-01" });
  if (url.pathname === "/rest/v1/profiles")
    return reply([{ id: userId, handle: "Reader", role: "member" }]);
  if (url.pathname === "/rest/v1/fan_art") return reply(artRows);
  if (url.pathname.startsWith("/storage/v1/object/fanart-private/") && req.method === "POST") {
    stored.set(url.pathname.split("/").at(-1), Buffer.from(await req.arrayBuffer()));
    return reply({});
  }
  if (url.pathname === "/storage/v1/object/list/fanart-private") {
    const { prefix } = await req.json();
    assert.equal(prefix, userId + "/");
    return reply([...stored.keys()].map((name) => ({ id: userId, name })));
  }
  if (url.pathname === "/storage/v1/object/fanart-private" && req.method === "DELETE") {
    for (const key of (await req.json()).prefixes) stored.delete(key.split("/").at(-1));
    return reply([]);
  }
  if (url.pathname === "/rest/v1/rpc/submit_fan_art") {
    registered = await req.json();
    return reply(userId);
  }
  if (url.pathname === "/rest/v1/newsletter_subscribers") return reply([]);
  if (url.pathname === "/auth/v1/admin/users/" + userId && req.method === "DELETE") {
    accountDeleted = true;
    return reply({});
  }
  throw new Error("Unexpected test request " + req.method + " " + url.pathname);
}

before(async () => {
  const script = await build({
    entryPoints: [path.join(__dirname, "../src/community.ts")],
    bundle: true,
    write: false,
    format: "esm",
    external: ["node:*"],
  });
  runtime = new Miniflare(
    convertV4MiniflareOptions({
      modules: true,
      script: script.outputFiles[0].text,
      compatibilityDate: "2026-10-13",
      compatibilityFlags: ["nodejs_compat"],
      host: "127.0.0.1",
      port: 0,
      outboundService: upstream,
      images: { binding: "IMAGES" },
      bindings: {
        PUBLIC_SITE_ORIGIN: site,
        SUPABASE_URL: database,
        SUPABASE_PUBLISHABLE_KEY: "sb_publishable_mock",
        SUPABASE_SECRET_KEY: "sb_secret_mock",
        RESEND_API_KEY: "local-test",
        EMAIL_FROM: "test@example.invalid",
        TURNSTILE_SITE_KEY: "widget",
        TURNSTILE_SECRET_KEY: "local-test",
        NEWSLETTER_TOKEN_SECRET: newsletterSecret,
      },
    }),
  );
  await runtime.ready;
});
after(async () => {
  await runtime?.dispose();
});
function reset() {
  calls = [];
  stored = new Map();
  artRows = [];
  registered = undefined;
  accountDeleted = false;
}
function url(op) {
  return site + "/api/community?op=" + op;
}
function post(body) {
  return { method: "POST", headers: { Origin: site, Cookie: "ha_access=session-value" }, body };
}

test("status exposes only public session configuration, and a cross-origin mutation is refused before contacting providers", async () => {
  reset();
  const status = await runtime.dispatchFetch(url("status"));
  assert.deepEqual(await status.json(), {
    configured: true,
    turnstileSiteKey: "widget",
    user: null,
  });
  assert.equal(status.headers.get("Cache-Control"), "no-store");
  const rejected = await runtime.dispatchFetch(url("login"), {
    method: "POST",
    headers: { Origin: "https://other.example" },
  });
  assert.equal(rejected.status, 403);
  assert.equal(calls.length, 0);
});
test("login emits two HttpOnly cookies and hides session tokens from JSON", async () => {
  reset();
  const response = await runtime.dispatchFetch(
    url("login"),
    post(
      JSON.stringify({
        email: "reader@example.invalid",
        password: "test-password-long",
        turnstileToken: "login-test-token",
      }),
    ),
  );
  assert.deepEqual(await response.json(), { signedIn: true });
  const cookies = response.headers.getSetCookie();
  assert.equal(cookies.length, 2);
  for (const cookie of cookies)
    assert.match(cookie, /HttpOnly; SameSite=Lax; Path=\/; Max-Age=\d+; Secure/);
});
test("email scanners may read a French confirmation page without consuming its signed unsubscribe token", async () => {
  reset();
  const token = createHmac("sha256", newsletterSecret)
    .update("unsubscribe:" + userId)
    .digest("hex");
  const target = url("newsletter-unsubscribe") + "&locale=fr&id=" + userId + "&token=" + token;
  const response = await runtime.dispatchFetch(target);
  assert.match(await response.text(), /method="post"/);
  assert.equal(response.headers.get("Referrer-Policy"), "strict-origin");
  assert.equal(calls.length, 0);
  const confirmed = await runtime.dispatchFetch(target, { method: "POST" });
  assert.equal(confirmed.status, 200);
  assert.deepEqual(calls, [["PATCH", "/rest/v1/newsletter_subscribers"]]);
});
test("Images converts a real multipart PNG to a private WebP before registering its moderation record", async () => {
  reset();
  const form = new FormData();
  for (const [key, value] of Object.entries({
    sitePermission: "true",
    authorDeclaration: "true",
    rightsUnderstanding: "true",
    title: "Test work",
    description: "A test illustration",
    alt: "A green rectangle",
    game: "Test",
    displayName: "Reader",
  }))
    form.set(key, value);
  form.set("file", new Blob([png], { type: "image/png" }), "sample.png");
  const encoded = new Response(form);
  const init = post(await encoded.arrayBuffer());
  init.headers["Content-Type"] = encoded.headers.get("Content-Type");
  const response = await runtime.dispatchFetch(url("fan-art-submit"), init);
  assert.equal(response.status, 200, await response.clone().text());
  assert.deepEqual(await response.json(), { id: userId, pending: true });
  assert.equal(registered.p_author_id, userId);
  assert.equal(registered.p_newsletter, false);
  const image = stored.get(registered.p_key.split("/").at(-1));
  assert.equal(image.toString("ascii", 0, 4), "RIFF");
  assert.equal(image.toString("ascii", 8, 12), "WEBP");
  const binding = await runtime.getImagesBinding("IMAGES");
  const info = await binding.info(new Blob([image]).stream());
  assert.equal(info.width, 125);
  assert.equal(info.height, 100);
});
test("account removal verifies a large private gallery in bounded requests", async () => {
  reset();
  for (let i = 0; i < 55; i++) {
    const name = i.toString(16).padStart(32, "0") + ".webp";
    stored.set(name, png);
    artRows.push({ image_key: userId + "/" + name });
  }
  const response = await runtime.dispatchFetch(
    url("delete-account"),
    post(JSON.stringify({ password: "test-password-long" })),
  );
  assert.equal(response.status, 200, await response.clone().text());
  assert.equal(stored.size, 0);
  assert.equal(accountDeleted, true);
  assert.ok(calls.length < 15);
});
