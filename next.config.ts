import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async redirects() {
    return [
      {
        source: "/Historical_Daily_Reports",
        destination: "/archive",
        permanent: true,
      },
      {
        source:
          "/Historical_Daily_Reports/mining_people_broadcast_x_digest_:date.html",
        destination: "/daily/:date",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
