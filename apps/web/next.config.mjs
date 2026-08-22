/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["superdoc"],
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
