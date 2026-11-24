const path = require("path");
const { contentSecurityPolicy } = require("./csp.js");

const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: contentSecurityPolicy({
      apiBase: process.env.NEXT_PUBLIC_API_BASE_URL,
      dev: process.env.NODE_ENV !== "production",
    }),
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

/** @type {import("next").NextConfig} */
const nextConfig = {
  output: "standalone", // a self-contained server for the container image (frontend/Dockerfile)
  outputFileTracingRoot: path.join(__dirname),
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async redirects() {
    return [
      { source: "/upload", destination: "/cases/new", permanent: false },
      { source: "/report/:id", destination: "/reports/:id", permanent: false },
    ];
  },
};

module.exports = nextConfig;
