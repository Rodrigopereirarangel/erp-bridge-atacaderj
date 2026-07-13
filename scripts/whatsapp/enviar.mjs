#!/usr/bin/env node
// =============================================================================
// enviar.mjs — manda texto (e opcionalmente um arquivo) para um numero de
// WhatsApp, usando a sessao Baileys salva em ./auth.
// -----------------------------------------------------------------------------
// PRIMEIRA VEZ (login): rode  `node enviar.mjs --login`  e escaneie o QR que
// aparece no terminal com o WhatsApp do celular (Aparelhos conectados >
// Conectar um aparelho). A sessao fica salva em scripts/whatsapp/auth/
// (gitignored) e os envios seguintes sao silenciosos.
//
// Uso:
//   node enviar.mjs --login
//   node enviar.mjs --para 5521970117082 --texto "mensagem"
//   node enviar.mjs --para 5521970117082 --texto-arquivo resumo.txt --arquivo plan.xlsx
// =============================================================================
import { readFileSync } from 'node:fs';
import { basename, dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { adquirirLock, soltarLock } from './sessao-lock.mjs';

// mimetype correto por extensao — sem isso o WhatsApp entrega "arquivo
// generico" (octet-stream) e o celular nao sabe abrir (ex.: relatorio .html)
const MIMES = {
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.html': 'text/html',
  '.pdf': 'application/pdf',
  '.csv': 'text/csv',
  '.txt': 'text/plain',
};

const AQUI = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (n) => { const i = args.indexOf(n); return i !== -1 ? args[i + 1] : null; };
const LOGIN = args.includes('--login');
const PARA = opt('--para');
let TEXTO = opt('--texto');
const TEXTO_ARQ = opt('--texto-arquivo');
const ARQUIVO = opt('--arquivo');

if (!LOGIN && !PARA) {
  console.error('Uso: node enviar.mjs --login | --para <numero com DDI> --texto "..." [--arquivo x.xlsx]');
  process.exit(2);
}
if (TEXTO_ARQ) TEXTO = readFileSync(TEXTO_ARQ, 'utf8');

// lock de sessao compartilhado com colher-marcas.mjs (a sessao Baileys em
// ./auth e uma so — dois sockets simultaneos derrubam um ao outro). Envio e
// importante: espera ate 60s pela vez; se continuar ocupado, erro (padrao atual).
const LOCK = join(AQUI, '.sessao.lock');
if (!(await adquirirLock(LOCK, { esperarMs: 60000 }))) {
  console.error('[whatsapp] sessao em uso ha mais de 60s (colheita presa?) — abortando.');
  process.exit(1);
}
// solta em TODAS as saidas (sucesso, erro, timeout) — os process.exit abaixo
// disparam este handler; soltarLock so remove o lock se o PID for o nosso.
process.on('exit', () => soltarLock(LOCK));

const baileys = await import('@whiskeysockets/baileys');
const makeWASocket = baileys.default?.makeWASocket || baileys.makeWASocket || baileys.default;
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = baileys;
const qrcode = (await import('qrcode-terminal')).default;

const { state, saveCreds } = await useMultiFileAuthState(join(AQUI, 'auth'));
// a lib vem com uma versao do protocolo "engessada" no pacote; o WhatsApp
// rejeita handshakes de versoes antigas (erro 405 antes do QR aparecer) —
// por isso buscamos a versao atual do WhatsApp Web a cada conexao.
const { version: WA_VERSION } = await fetchLatestBaileysVersion();

const timeout = setTimeout(() => {
  console.error('[whatsapp] TIMEOUT: nao conectou em 120s. Sessao expirada? Rode --login de novo.');
  process.exit(1);
}, 120000);

function conectar() {
  const sock = makeWASocket({ auth: state, version: WA_VERSION, printQRInTerminal: false, syncFullHistory: false });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      if (LOGIN) { console.log('\nEscaneie com o WhatsApp do celular:\n'); qrcode.generate(qr, { small: true }); }
      else { console.error('[whatsapp] sessao inexistente/expirada — rode: node enviar.mjs --login'); process.exit(1); }
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.restartRequired) { conectar(); return; } // apos pairing
      console.error('[whatsapp] conexao fechou (code ' + code + ').');
      process.exit(code === DisconnectReason.loggedOut ? 1 : 3);
    }
    if (connection === 'open') {
      try {
        if (LOGIN) { console.log('[whatsapp] LOGIN OK — sessao salva em scripts/whatsapp/auth/'); }
        else {
          const jid = PARA.replace(/\D/g, '') + '@s.whatsapp.net';
          if (TEXTO) await sock.sendMessage(jid, { text: TEXTO });
          if (ARQUIVO) {
            await sock.sendMessage(jid, {
              document: readFileSync(ARQUIVO),
              fileName: basename(ARQUIVO),
              mimetype: MIMES[extname(ARQUIVO).toLowerCase()] || 'application/octet-stream',
            });
          }
          console.log('[whatsapp] enviado para ' + PARA + (ARQUIVO ? ' (texto + ' + basename(ARQUIVO) + ')' : ' (texto)'));
        }
        // da tempo do socket terminar os ACKs antes de sair
        setTimeout(() => process.exit(0), 4000);
      } catch (e) {
        console.error('[whatsapp] ERRO ao enviar: ' + e.message);
        process.exit(1);
      }
    }
  });
}
conectar();
