import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const token = request.cookies.get('auth_token')?.value;

    // request.formData() はNext.jsの内部でボディをパースするため、
    // 大きなファイル（>1MB）を含む場合にサイズ制限エラーが発生する。
    // ボディを一切パースせず、生のストリームをそのままバックエンドに転送することで回避する。
    // duplex:'half' はNode.js fetchでストリーミングbodyを使う際に必要だが
    // TypeScriptのRequestInit型に含まれないため、as anyで型チェックを回避する。
    const res = await fetch(`${BACKEND_URL}/api/analyze/deck`, {
      method: 'POST',
      headers: {
        'content-type': request.headers.get('content-type') || '',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      // @ts-ignore - Node.js fetch でリクエストボディをストリーミング転送する
      body: request.body,
      duplex: 'half',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}
