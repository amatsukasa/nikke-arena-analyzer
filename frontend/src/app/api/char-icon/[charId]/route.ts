import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable';
const NO_STORE_CACHE_CONTROL = 'no-store, no-cache, must-revalidate, max-age=0';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

export async function GET(request: NextRequest, { params }: { params: Promise<{ charId: string }> }) {
  try {
    const { charId } = await params;
    const normalizedId = charId.replace(/\.png$/i, '');
    const res = await fetch(`${BACKEND_URL}/api/char-icon/${encodeURIComponent(normalizedId)}.png`, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
      },
    });
    
    if (!res.ok) {
      return new NextResponse('Icon not found', {
        status: res.status,
        headers: {
          'Cache-Control': NO_STORE_CACHE_CONTROL,
        },
      });
    }

    const contentType = res.headers.get('content-type') || 'image/png';
    const fileBuffer = await res.arrayBuffer();

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': IMMUTABLE_CACHE_CONTROL,
      },
    });
  } catch (error: any) {
    return new NextResponse(error.message, {
      status: 500,
      headers: {
        'Cache-Control': NO_STORE_CACHE_CONTROL,
      },
    });
  }
}
