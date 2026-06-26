import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function forward(request: NextRequest, method: 'GET' | 'PUT') {
  try {
    const token = request.cookies.get('auth_token')?.value;
    const body = method === 'PUT' ? await request.text() : undefined;
    const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
      method,
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body ? { body } : {}),
    });
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { message: text || `Backend request failed (${response.status})` };
    }
    return NextResponse.json(data, {
      status: response.status,
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    return NextResponse.json(
      { message: error instanceof Error ? error.message : 'Request failed' },
      { status: 500 },
    );
  }
}

export async function GET(request: NextRequest) {
  return forward(request, 'GET');
}

export async function PUT(request: NextRequest) {
  return forward(request, 'PUT');
}
