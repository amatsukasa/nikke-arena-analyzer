import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

export async function POST(request: NextRequest) {
  try {
    const text = await request.text();
    if (!text) {
      return NextResponse.json(
        { message: 'リクエストボディが空です。' },
        { status: 400 }
      );
    }

    let password = '';
    try {
      const body = JSON.parse(text);
      password = body.password;
    } catch (e) {
      return NextResponse.json(
        { message: 'JSONの形式が正しくありません。' },
        { status: 400 }
      );
    }

    const sitePassword = process.env.SITE_PASSWORD;

    if (!sitePassword) {
      return NextResponse.json(
        { message: 'パスコード制限は無効になっています。' },
        { status: 400 }
      );
    }

    if (password === sitePassword) {
      // cookies() を await することで、Next.js 15 の非同期化に対応しつつ、14以前のバージョンでも動作させます。
      const cookieStore = await cookies();
      cookieStore.set('site_unlocked', password, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        path: '/',
        maxAge: 60 * 60 * 24 * 7, // 1週間有効
      });

      return NextResponse.json({ success: true });
    }

    return NextResponse.json(
      { message: 'パスコードが正しくありません。' },
      { status: 400 }
    );
  } catch (error: any) {
    console.error('パスコード検証APIエラー:', error);
    return NextResponse.json(
      { message: 'サーバーエラーが発生しました。', error: error.message },
      { status: 500 }
    );
  }
}
