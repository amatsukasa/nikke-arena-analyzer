import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  try {
    const { path } = await params;
    const filePath = path.join('/');
    const res = await fetch(`${BACKEND_URL}/api/uploads/${filePath}`, {
      method: 'GET',
      cache: 'no-store',
    });
    
    if (!res.ok) {
      return new NextResponse('File not found', { status: 404 });
    }

    const contentType = res.headers.get('content-type') || 'application/octet-stream';
    const fileBuffer = await res.arrayBuffer();
    const isTemporaryCrop = filePath.startsWith('cropped/crop_');

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': isTemporaryCrop
          ? 'no-store, no-cache, must-revalidate, max-age=0'
          : 'public, max-age=31536000, immutable',
      },
    });
  } catch (error: any) {
    return new NextResponse(error.message, { status: 500 });
  }
}
