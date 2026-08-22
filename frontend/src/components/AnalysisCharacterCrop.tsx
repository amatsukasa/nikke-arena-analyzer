"use client";

import { useEffect, useState } from "react";

interface AnalysisCharacterCropProps {
  imageUrl?: string | null;
  alt: string;
  fallback: string;
  className: string;
}

export default function AnalysisCharacterCrop({ imageUrl, alt, fallback, className }: AnalysisCharacterCropProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [imageUrl]);

  return (
    <div className={`${className} relative shrink-0 overflow-hidden bg-slate-800/50 ring-1 ring-white/5`}>
      <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">{fallback}</div>
      {imageUrl && !failed && (
        <img
          key={imageUrl}
          src={imageUrl}
          alt={alt}
          loading="lazy"
          decoding="async"
          className="relative h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
