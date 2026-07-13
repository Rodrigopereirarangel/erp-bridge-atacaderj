#!/usr/bin/env node
// Colhe mensagens "MARCAS <round>: cod=TOK ..." recebidas no WhatsApp do ponte
// e grava/mescla no data/feedback do detector. NUNCA lanca: qualquer problema
// -> log e exit 0 (a proxima colheita tenta de novo).
import { readFileSync, existsSync, writeFileSync, unlinkSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseMarcas, mesclarFeedback } from "./marcas-parser.mjs";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = join(AQUI, "..", "..");
const LOCK = join(AQUI, ".colher.lock");

function log(msg) { console.log(`[colher-marcas] ${msg}`); }

// lock por PID (nao brigar com enviar.mjs / colheita anterior)
try {
  if (existsSync(LOCK)) {
    const pid = Number(readFileSync(LOCK, "utf8"));
    try { process.kill(pid, 0); log(`sessao em uso (pid ${pid}) — saindo`); process.exit(0); }
    catch { /* stale */ }
  }
  writeFileSync(LOCK, String(process.pid));
} catch { process.exit(0); }
const solta = () => { try { unlinkSync(LOCK); } catch {} };

let cfg = {};
try { cfg = JSON.parse(readFileSync(join(RAIZ, "config.local.json"), "utf8")); } catch {}
const M = cfg.marcas || {};
const FEEDBACK_DIR = M.feedbackDir || "C:/Users/User/detector-ruptura-atacaderj/data/feedback";
const REMETENTES = (M.remetentes || []).map((n) => String(n).replace(/\D/g, ""));

const baileys = await import("@whiskeysockets/baileys");
const makeWASocket = baileys.default?.makeWASocket || baileys.makeWASocket || baileys.default;
const { useMultiFileAuthState, fetchLatestBaileysVersion } = baileys;
const { state, saveCreds } = await useMultiFileAuthState(join(AQUI, "auth"));
const { version } = await fetchLatestBaileysVersion();

let colhidas = 0;
const fim = (code) => { solta(); process.exit(code); };
setTimeout(() => { log(`fim da janela — ${colhidas} mensagem(ns) de marcas`); fim(0); }, 25000);

try {
  const sock = makeWASocket({ auth: state, version, printQRInTerminal: false, syncFullHistory: false });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", (u) => {
    if (u.qr) { log("sessao expirada — rode enviar.mjs --login"); fim(0); }
    if (u.connection === "close") fim(0);
  });
  sock.ev.on("messages.upsert", ({ messages }) => {
    for (const msg of messages || []) {
      try {
        const de = String(msg.key?.remoteJid || "").replace(/\D/g, "");
        if (REMETENTES.length && !REMETENTES.some((r) => de.includes(r))) continue;
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
