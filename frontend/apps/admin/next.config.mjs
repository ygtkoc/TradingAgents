/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: [
    "@ta/ui",
    "@ta/utils",
    "@ta/config",
    "@ta/query",
    "@ta/schemas",
    "@ta/supabase",
    "@ta/types",
  ],
};

export default nextConfig;
