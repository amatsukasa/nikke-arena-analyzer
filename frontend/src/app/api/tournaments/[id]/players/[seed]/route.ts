import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string; seed: string }> }) {
  try {
    const { id, seed } = await params;
    const body = await request.json();
    const token = request.cookies.get('auth_token')?.value;

    const res = await fetch(`${BACKEND_URL}/api/tournaments/${id}/players/${seed}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...(token ? { 'Cookie': `auth_token=${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    
    // If response is not JSON, handle it safely
    let data;
    try {
      data = await res.json();
    } catch {
      data = { message: 'Success' };
    }
    
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}
