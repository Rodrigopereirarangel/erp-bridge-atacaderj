#!/usr/bin/env node
// Colhe mensagens "MARCAS <round>: cod=TOK ..." recebidas no WhatsApp do ponte
// e grava/mescla no data/feedback do detector. NUNCA lanca: qualquer problema
// (lock, config, baileys, auth/ corrompida, node_modules quebrado) -> log e
// exit 0 (a proxima colheita horaria tenta de novo).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseMarcas, mesclarFeedback, remetentePermitido } from "./marcas-parser.mjs";
import { adquirirLock, soltarLock } from "./sessao-lock.mjs";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, "..", "..");
const LOCK = join(AQUI, ".sessao.lock");

function log(msg) { console.log(`[colher-marcas] ${msg}`); }

// solta/fim definidos ANTES de qualquer await: qualquer falha dali em diante
// ja consegue liberar o lock e sair limpo.
const solta = () => soltarLock(LOCK);
const fim = (code) => { solta(); process.exit(code); };

// lock de sessao compartilhado com enviar.mjs (a sessao Baileys e uma so).
// Ocupado -> sai na hora: a proxima colheita pega.
let temLock = false;
try { temLock = await adquirirLock(LOCK); } catch { /* fs indisponivel */ }
if (!temLock) { log("sessao em uso — saindo"); process.exit(0); }

let cfg = {};
try { cfg = JSON.parse(readFileSync(join(RAIZ, "config.local.json"), "utf8")); } catch {}
const M = cfg.marcas || {};
const FEEDBACK_DIR = M.feedbackDir || "C:/Users/User/detector-ruptura-atacaderj/data/feedback";
const REMETENTES = M.remetentes || []; // normalizados dentro de remetentePermitido()

let colhidas = 0;
// janela fixa de colheita — vale mesmo se o setup abaixo travar (rede lenta etc.)
setTimeout(() => { log(`fim da janela — ${colhidas} mensagem(ns) de marcas`); fim(0); }, 25000);

// TODO o setup pos-lock guardado: import do baileys, leitura da auth/, busca
// de versao e socket. Qualquer excecao vira log + fim(0).
try {
  const baileys = await import("@whiskeysockets/baileys");
  const makeWASocket = baileys.default?.makeWASocket || baileys.makeWASocket || baileys.default;
  const { useMultiFileAuthState, fetchLatestBaileysVersion } = baileys;
  const { state, saveCreds } = await useMultiFileAuthState(join(AQUI, "auth"));
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({ auth: state, version, printQRInTerminal: false, syncFullHistory: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", (u) => {
    if (u.qr) { log("sessao expirada — rode enviar.mjs --login"); fim(0); }
    if (u.connection === "close") fim(0);
  });
  sock.ev.on("messages.upsert", ({ messages }) => {
    for (const msg of messages || []) {
      try {
        // allowlist tolerante ao quirk do 9o digito do JID brasileiro
        // (5521970117082 pode chegar como 552170117082) — match pelos
        // ultimos 8 digitos, feito em remetentePermitido() (puro, testado).
        const de = String(msg.key?.remoteJid || "").replace(/\D/g, "");
        if (!remetentePermitido(de, REMETENTES)) continue;
        const texto = msg.message?.conversation || msg.message?.extendedTextMessage?.text || "";
        const r = parseMarcas(texto);
        if (!r) continue;
        mesclarFeedback(FEEDBACK_DIR, r.roundId, r.marcas, new Date().toISOString());
        colhidas++;
        log(`gravado ${Object.keys(r.marcas).length} marca(s) na rodada ${r.roundId}`);
      } catch (e) { log(`mensagem ignorada: ${e.message}`); }
    }
  });
} catch (e) { log(`erro: ${e.message}`); fim(0); }
