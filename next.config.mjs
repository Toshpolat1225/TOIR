/** @type {import('next').NextConfig} */
const nextConfig = {
  // Оптимизация пакетов - уменьшает размер бандла
  experimental: {
    optimizePackageImports: [
      'lucide-react',
      '@radix-ui/react-icons',
      'recharts',
      'date-fns',
    ],
  },
  
  // Изображения - включаем оптимизацию
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 32, 48, 64, 96, 128, 256],
  },
  
  // Безопасность
  poweredByHeader: false,
  
  // Сжатие
  compress: true,
  
  // Строгий режим React для выявления проблем
  reactStrictMode: true,

  // Редиректы: /os -> Осн. средства
  async redirects() {
    return [
      { source: '/os', destination: '/dashboard/os', permanent: false },
    ]
  },
  
  // Webpack оптимизации
  webpack: (config, { isServer }) => {
    // Оптимизация для клиентского бандла
    if (!isServer) {
      config.optimization.splitChunks = {
        chunks: 'all',
        cacheGroups: {
          recharts: {
            test: /[\\/]node_modules[\\/](recharts|d3-.*)[\\/]/,
            name: 'recharts',
            priority: 10,
            reuseExistingChunk: true,
          },
          radix: {
            test: /[\\/]node_modules[\\/]@radix-ui[\\/]/,
            name: 'radix-ui',
            priority: 10,
            reuseExistingChunk: true,
          },
        },
      }
    }
    return config
  },
}

export default nextConfig
