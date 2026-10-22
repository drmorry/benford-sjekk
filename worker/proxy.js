// CORS proxy for Benford-sjekk, as a Cloudflare Worker.
//
// Only answers requests coming from the origins in ALLOWED_ORIGINS, so it
// can't be used as an open proxy by other websites.
//
// Usage from the app:  https://<worker>.workers.dev/?url={url}

const ALLOWED_ORIGINS = ["https://drmorry.github.io", "http://localhost:5000", "http://127.0.0.1:5000"];

export default {
  async fetch(request) {
    const origin = request.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
      "Access-Control-Expose-Headers": "X-Final-URL",
      Vary: "Origin",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "GET") return new Response("Bare GET", { status: 405, headers: cors });
    if (!ALLOWED_ORIGINS.includes(origin)) return new Response("Ikke tillatt opprinnelse", { status: 403, headers: cors });

    const target = new URL(request.url).searchParams.get("url") || "";
    if (!/^https?:\/\//i.test(target)) return new Response("Mangler ?url=", { status: 400, headers: cors });

    let upstream;
    try {
      upstream = await fetch(target, {
        headers: { "User-Agent": "BenfordSjekk/1.0" },
        redirect: "follow",
        cf: { cacheTtl: 300 },
      });
    } catch (err) {
      return new Response("Feil ved henting: " + err.message, { status: 502, headers: cors });
    }
    const headers = new Headers(cors);
    headers.set("Content-Type", upstream.headers.get("Content-Type") || "application/octet-stream");
    headers.set("X-Final-URL", upstream.url);
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
