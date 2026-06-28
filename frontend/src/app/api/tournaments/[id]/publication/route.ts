import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function proxyPublication(
  request: NextRequest,
  id: string,
  method: 'GET' | 'PUT',
) {
  const token = request.cookies.get('auth_token')?.value;
  const body = method === 'PUT' ? JSON.stringify(await request.json()) : undefined;
  const res = await fetch(`${BACKEND_URL}/api/tournaments/${id}/publication`, {
    method,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  return NextResponse.json(data, { status: res.status });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    return await proxyPublication(request, id, 'GET');
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    return await proxyPublication(request, id, 'PUT');
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}
