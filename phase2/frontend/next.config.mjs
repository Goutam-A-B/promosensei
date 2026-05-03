/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**.amazon.in" },
      { protocol: "https", hostname: "**.media-amazon.com" },
      { protocol: "https", hostname: "**.flipkart.com" },
      { protocol: "https", hostname: "**.nykaa.com" }
    ]
  }
};

export default nextConfig;
