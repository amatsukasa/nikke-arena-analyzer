import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    console.log("[cross-tournament/stats] body", body);

    const hasTournamentIds = Array.isArray(body.tournament_ids) && body.tournament_ids.length > 0;

    if (!hasTournamentIds) {
      return NextResponse.json(
        {
          total_players: 0,
          total_matches: 0,
          character_stats: [],
          team_usage: [],
          matchups: [],
          message: "分析対象が未選択です",
        },
        { status: 200 }
      );
    }

    const res = await fetch(`${BACKEND_URL}/api/dashboard/cross-tournament/stats`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json({ message: error.message }, { status: 500 });
  }
}
