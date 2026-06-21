import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    
    // httpOnly クッキーをサーバーサイドから削除する
    cookieStore.set('site_session', '', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 0,
    });

    cookieStore.set('auth_token', '', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 0,
    });
    
    cookieStore.set('role', '', {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 0,
    });

    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('ログアウトAPIエラー:', error);
    return NextResponse.json(
      { message: 'サーバーエラーが発生しました。', error: error.message },
      { status: 500 }
    );
  }
}
