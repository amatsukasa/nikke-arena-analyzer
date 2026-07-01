import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
  'Pragma': 'no-cache',
  'Expires': '0',
};

async function readBackendResponse(res: Response) {
  const text = await res.text();
  if (!text) {
    return res.ok ? {} : { message: `Backend request failed (${res.status})` };
  }

  try {
    return JSON.parse(text);
  } catch {
    return {
      message: res.ok
        ? text
        : `Backend request failed (${res.status}): ${text}`,
    };
  }
}

export async function GET(request: NextRequest) {
  try {
    const token = request.cookies.get('auth_token')?.value;
    const query = request.nextUrl.searchParams.toString();
    const url = `${BACKEND_URL}/api/tournaments${query ? `?${query}` : ''}`;
    const res = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
    });

    console.log("[api/tournaments] BACKEND_URL", BACKEND_URL);
    console.log("[api/tournaments] token exists", Boolean(token));
    console.log("[api/tournaments] token prefix", token?.slice(0, 20));
    console.log("[api/tournaments] forward url", url);
    console.log("[api/tournaments] backend status", res.status);

    const data = await readBackendResponse(res);
    console.log("[api/tournaments] backend response", data);
    return NextResponse.json(data, {
      status: res.status,
      headers: NO_CACHE_HEADERS,
    });
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const token = request.cookies.get('auth_token')?.value;

    const res = await fetch(`${BACKEND_URL}/api/tournaments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    const data = await readBackendResponse(res);
    return NextResponse.json(data, {
      status: res.status,
      headers: NO_CACHE_HEADERS,
    });
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}
