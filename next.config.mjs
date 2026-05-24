/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ["@google/genai", "gifenc", "jszip"]
  }
};

export default nextConfig;


