/** Original illustration: Mount Ararat (Masis & Sis) behind a stylised Yerevan skyline. */
export function SkylineArt({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 800 220"
      className={className}
      role="img"
      aria-label="Illustration of Mount Ararat rising behind the Yerevan skyline"
      preserveAspectRatio="xMidYMax slice"
    >
      <g fill="currentColor">
        {/* Ararat */}
        <path
          opacity="0.18"
          d="M120 200 L330 60 Q350 48 372 58 L470 120 L520 96 Q535 90 550 98 L660 200 Z"
        />
        <path opacity="0.35" d="M318 70 Q350 46 382 64 L402 78 L380 84 L362 74 L344 86 L330 78 Z" />
        <path opacity="0.3" d="M512 100 Q535 88 556 102 L566 110 L548 112 L534 104 L520 112 Z" />
        {/* Skyline */}
        <g opacity="0.55">
          <rect x="0" y="168" width="60" height="52" />
          <rect x="64" y="150" width="34" height="70" />
          <rect x="102" y="176" width="48" height="44" />
          {/* Cascade steps */}
          <path d="M160 220 V190 H190 V178 H220 V166 H250 V154 H280 V220 Z" />
          <rect x="292" y="140" width="22" height="80" />
          <path d="M318 220 V170 Q340 150 362 170 V220 Z" />
          {/* Opera house dome */}
          <path d="M372 220 V182 H452 V220 Z" />
          <path d="M392 182 Q412 156 432 182 Z" />
          <rect x="462" y="120" width="18" height="100" />
          <polygon points="462,120 471,104 480,120" />
          <rect x="488" y="160" width="44" height="60" />
          {/* Mother Armenia pedestal */}
          <rect x="544" y="146" width="16" height="74" />
          <rect x="549" y="126" width="6" height="20" />
          <rect x="570" y="172" width="60" height="48" />
          <rect x="636" y="152" width="30" height="68" />
          <rect x="672" y="178" width="58" height="42" />
          <rect x="736" y="160" width="64" height="60" />
        </g>
      </g>
    </svg>
  );
}

export function SkylineHero({ children }: { children: React.ReactNode }) {
  return (
    <section className="relative overflow-hidden bg-hero text-hero-foreground">
      <SkylineArt className="pointer-events-none absolute inset-x-0 bottom-0 h-40 w-full text-hero-foreground sm:h-52" />
      <div className="relative mx-auto max-w-7xl px-4 pb-24 pt-10 sm:px-6 sm:pb-32 sm:pt-14">
        {children}
      </div>
    </section>
  );
}
