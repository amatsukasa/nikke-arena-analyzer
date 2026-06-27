import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
      return new NextResponse('Icon not found', { status: 404 });
    }

    const contentType = res.headers.get('content-type') || 'image/png';
    const fileBuffer = await res.arrayBuffer();

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    });
  } catch (error: any) {
    return new NextResponse(error.message, { status: 500 });
  }
}
