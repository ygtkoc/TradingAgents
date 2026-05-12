/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@ta/ui", "@ta/utils", "@ta/config"],
  experimental: { typedRoutes: false },
};

export default nextConfig;
