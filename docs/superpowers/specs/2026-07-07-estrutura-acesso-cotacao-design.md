# Design — Estrutura geral de acesso: cotação via HTML injetado em pasta compartilhada

**Data:** 2026-07-07 · **Status:** aprovado pelo usuário (brainstorm de 2026-07-07)

## Contexto e decisões de escopo

- O bridge (este repo) extrai do MySQL do ERP (viewer só-leitura) e gera
  `produtos.json` + CSVs, agendado no PC-ponte (`DESKTOP-3BLTBIV`, 24h, rede da loja).
- **Decisão (2026-07-07): o loop de feedback (apelidos/correções) foi descartado.**
  Saiu do checklist e do escopo. O bridge é só extração → arquivos.
- **Decisão (2026-07-07): o funcionário nunca acessa o repositório.** GitHub guarda
  só código e memória do projeto (STATUS/specs). O único contato do funcionário com
  o sistema é um atalho que abre a cotação no navegador.
- Cenário A segue inegociável: **custo/preço não saem da rede da loja.**

## Como o funcionário acessa

Atalho "Cotação AtacadeRJ" na área de trabalho dos PCs da loja, apontando para
`\\DESKTOP-3BLTBIV\cotacao\cotacao.html`. Dois cliques → navegador abre a página
com o catálogo da última rodada do bridge. Sem conta, sem senha, sem URL digitada,
sem GitHub.

## Fluxo de dados (mudança em relação ao plano anterior)

O plano anterior era servir `produtos.json` por HTTP e o HTML fazer `fetch`.
**Substituído por injeção sem servidor:**

1. O bridge roda agendado (catálogo 08/12/15/18h) e extrai o catálogo como hoje.
2. Passo novo de projeção: o bridge pega o **template** do HTML da cotação
   (o app do repo `cotacao-auditoria-atacaderj`, que já funciona com catálogo
   embutido) e **substitui o bloco marcado do catálogo** pelos dados recém-extraídos.
3. Grava `cotacao.html` completo na pasta compartilhada, com **escrita atômica**
   (grava `cotacao.html.tmp` e renomeia por cima). Ninguém abre arquivo pela metade.
4. Se a extração falhar, nada é gravado: o `cotacao.html` da última rodada boa
   permanece — a cotação nunca sai do ar.

Os CSVs dos detectores continuam exatamente como estão. O `produtos.json` continua
sendo gerado (outros consumidores o usam); a cotação apenas deixa de depender dele
em tempo de abertura.

**Por que sem servidor:** um mini-site HTTP no ponte seria um processo 24h a mais,
que pode cair sem ninguém perceber. Pasta compartilhada é servida pelo próprio
Windows — não existe peça nova para travar.

## Mudanças concretas

### Repo `cotacao-auditoria-atacaderj` (app da cotação)
- Padronizar o bloco do catálogo embutido com um marcador único e estável:
  `<script id="catalogo-dados">…</script>`, para o bridge localizar e substituir
  com segurança. Sem mudança de comportamento ou visual.

### Repo `erp-bridge-atacaderj` (este)
- Novo módulo `src/inject_html.py`: lê o template, valida a presença do marcador
  `catalogo-dados`, injeta o catálogo, grava atômico.
- `config.local.json` ganha duas chaves em `saida`:
  - `cotacao_html_template` — caminho do HTML-molde (clone do repo da cotação no ponte;
    atualiza com `git pull` quando o app evoluir);
  - `cotacao_html_saida` — caminho final na pasta compartilhada.
- `--demo` também gera `cotacao.html` com dados falsos, para validar o app de ponta
  a ponta sem tocar o ERP.
- Falha dura e explícita se o marcador não for encontrado no template (protege
  contra template desatualizado).

### PC-ponte (setup único, manual)
- Compartilhar a pasta de saída da cotação na rede como **somente leitura**
  (`\\DESKTOP-3BLTBIV\cotacao`).
- Criar o atalho nos PCs dos funcionários.

## Segurança

- Custo/preço permanecem na rede local (pasta compartilhada só-leitura; GitHub sem dados).
- Sem porta nova, sem serviço novo, sem credencial nova. O viewer segue só-`SELECT`
  com a trava do `src/db.py`.

## Testes

- `python src/bridge.py --demo` → `cotacao.html` com dados falsos abre e cota.
- Teste do marcador: template sem marcador → o bridge falha com mensagem clara e
  **não** sobrescreve o arquivo publicado.
- Teste de atomicidade: arquivo publicado nunca existe em estado parcial.

## Fora de escopo

- Loop de feedback (apelidos/correções) — descartado.
- Auditoria (`dashboard.html`) — ferramenta do Rodrigo, não entra no acesso do funcionário.
- Pricing semanal — design separado, entra depois.
