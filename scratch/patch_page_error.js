const fs = require('fs');
const path = 'src/app/page.tsx';

if (!fs.existsSync(path)) {
  console.error("File not found:", path);
  process.exit(1);
}

let code = fs.readFileSync(path, 'utf8');

const targetStr = `  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );`;

const replacementStr = `  if (loading) return (
    <div className="flex h-screen items-center justify-center">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );

  if (allTournaments.length === 0) {
    return (
      <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans">
        <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-slate-900/80 backdrop-blur-md">
          <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="text-xl font-black tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">
                NIKKE ARENA ANALYZER
              </span>
            </div>
            <div className="flex items-center space-x-4">
              <a href="/tournaments/manage" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-bold transition-all shadow-lg shadow-blue-500/20">
                大会データ登録
              </a>
            </div>
          </div>
        </header>
        
        <main className="flex-1 max-w-4xl mx-auto px-4 py-16 flex flex-col items-center justify-center text-center">
          <div className="w-24 h-24 rounded-3xl bg-slate-900 border border-white/10 flex items-center justify-center mb-8 shadow-2xl">
            <span className="text-4xl">📊</span>
          </div>
          <h1 className="text-3xl font-black mb-4 tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            大会分析ダッシュボードへようこそ
          </h1>
          <p className="text-slate-400 text-base max-w-md mb-8 leading-relaxed">
            現在、システムに大会データが登録されていません。<br />
            まずは右上の「大会データ登録」ボタンから、対戦結果データをインポートしてください。
          </p>
          <a href="/tournaments/manage" className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold transition-all shadow-xl shadow-blue-500/20">
            <span>大会データ登録へ移動</span>
          </a>
        </main>
      </div>
    );
  }`;

// 改行コード（CRLF / LF）に依存しない置換
const codeNormalized = code.replace(/\r\n/g, '\n');
const targetNormalized = targetStr.replace(/\r\n/g, '\n');
const replacementNormalized = replacementStr.replace(/\r\n/g, '\n');

if (codeNormalized.includes(targetNormalized)) {
  const patched = codeNormalized.replace(targetNormalized, replacementNormalized);
  // もとの改行コード（WindowsならCRLF）に戻して保存
  const isCRLF = code.includes('\r\n');
  const finalCode = isCRLF ? patched.replace(/\n/g, '\r\n') : patched;
  fs.writeFileSync(path, finalCode, 'utf8');
  console.log("Success: Patched page.tsx using Node.js");
} else {
  console.error("Error: Target string not found in page.tsx");
}
