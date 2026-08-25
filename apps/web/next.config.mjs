/** @type {import('next').NextConfig} */

/*
  The signing service's own screens, served through this origin.

  Placing a signature box on a PDF is their screen and should stay theirs: the
  code that places the field is the code that later stamps the signature, so
  the coordinates are correct by construction. What was wrong was the seam.
  Opening it on its own origin meant a second sign-in, because a browser keeps
  session state per origin and nothing on this platform can write into theirs.

  Proxying their routes here makes them same-origin, so the session can be
  seeded before the frame loads and the person placing fields signs in once,
  here. Their asset paths are absolute, which is why /assets and /env.js are
  forwarded too; neither collides with anything this application serves, since
  Next puts its own under /_next.

  This is a seam, and it is worth saying so. It depends on their client's URLs
  staying where they are. If they move, this breaks visibly at the frame rather
  than silently, and the fallback is the direct link.
*/
const SIGNING = process.env.OPENSIGN_CLIENT_URL ?? "http://localhost:3200";

const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["superdoc"],
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [
      { source: "/placeHolderSign/:path*", destination: `${SIGNING}/placeHolderSign/:path*` },
      { source: "/signaturePdf/:path*", destination: `${SIGNING}/signaturePdf/:path*` },
      { source: "/recipientSignPdf/:path*", destination: `${SIGNING}/recipientSignPdf/:path*` },
      { source: "/assets/:path*", destination: `${SIGNING}/assets/:path*` },
      { source: "/env.js", destination: `${SIGNING}/env.js` },
    ];
  },
};

export default nextConfig;
