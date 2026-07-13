// Lock de sessao compartilhado entre enviar.mjs e colher-marcas.mjs.
// A sessao Baileys em ./auth e UMA so — dois sockets simultaneos derrubam
// um ao outro. Quem for usar a sessao adquire o lock primeiro (arquivo com
// o PID do dono); PID morto = lock stale, pode assumir.
import { existsSync, readFileSync, writeFileSync, unlinkSync } from "node:fs";

function pidVivo(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function tentar(caminho) {
  if (existsSync(caminho)) {
    const pid = Number(readFileSync(caminho, "utf8"));
    if (pid && pidVivo(pid)) return false; // ocupado por processo vivo
    // stale (PID morto ou arquivo vazio/corrompido) — assume
  }
  writeFileSync(caminho, String(process.pid));
  return true;
}

// Tenta adquirir o lock. esperarMs=0 -> uma tentativa so; esperarMs>0 ->
// re-tenta a cada intervaloMs ate estourar o prazo. Retorna true/false.
export async function adquirirLock(caminho, { esperarMs = 0, intervaloMs = 1000 } = {}) {
  const limite = Date.now() + esperarMs;
  for (;;) {
    if (tentar(caminho)) return true;
    if (Date.now() + intervaloMs > limite) return false;
    await new Promise((r) => setTimeout(r, intervaloMs));
  }
}

// Solta o lock — so remove se for NOSSO (nunca apaga o lock de outro processo vivo).
export function soltarLock(caminho) {
  try {
    if (Number(readFileSync(caminho, "utf8")) === process.pid) unlinkSync(caminho);
  } catch { /* ja nao existe ou nao e nosso */ }
}
