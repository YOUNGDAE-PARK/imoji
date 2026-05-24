/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',

  images: {
    unoptimized: true,
  },

  experimental: {
    serverComponentsExternalPackages: ["@google/genai", "gifenc", "jszip"]
  }
};

export default nextConfig;


