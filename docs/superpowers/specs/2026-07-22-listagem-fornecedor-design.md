# Listagem de produtos por fornecedor — design

Data: 2026-07-22 · Status: aprovado em conversa com o dono (respostas registradas no fim)

## Objetivo

Relatório HTML único, aberto direto no navegador (PC/celular), com uma barra para
escolher o fornecedor. Ao escolher, lista os produtos daquele fornecedor com:

| coluna | fonte |
|--------|-------|
| código | catálogo do bridge (`cdProduto`) |
| produto (nomenclatura) | catálogo do bridge (`nmProdutoPai`) |
| curva | catálogo do bridge (`CURVA_ABC`) — exibida porque muda a regra de ruptura |
| corredor | estado do app `deposito-atacaderj` no ponte (código→rua), rótulo oficial "A1 bisc1"…"A25 TERREO" |
| estoque mínimo no depósito | mediana de janelas rolantes de 45 dias (regra abaixo), em caixa-mãe |

Só produtos **ativos** entram.

## Arquitetura (decisão: abordagem A)

- **erp-bridge-atacaderj** (só extração, padrão do ecossistema): ganha as queries/
  exports novos — negociação por produto×fornecedor, entradas por produto×fornecedor
  dos últimos 6 meses, e vendas diárias de 180 dias. Roda no agendamento que já existe.
- **Este repo** (`listagem-fornecedor-atacaderj`): script Python que lê os arquivos do
  bridge + o estado de ruas do depósito, calcula fornecedor e estoque mínimo de cada
  produto e gera `saida/listagem-fornecedores.html` (arquivo único, dados embutidos,
  sem dependência externa).
- Roda no PC-ponte. **SEM tarefa agendada por enquanto** (decisão do dono, 22/07):
  geração manual (script/`.bat`) durante a fase de teste. Agendar (~06:00, depois do
  bridge da madrugada) só depois de o dono validar os números.
- Se a geração falhar (insumo ausente, query quebrada), o HTML anterior permanece no
  ar e o erro vai para o log. O cabeçalho do HTML mostra "dados de DD/MM hh:mm".

## Regra 1 — fornecedor de cada produto (cada produto aparece em UM só)

1. Produto com negociação (`tbNegociacao`) cuja pessoa comercial é **"COTACAO"**
   (cdPessoa 164259) → entra em **COTACAO**, sempre (validado no ERP: óleo Soya).
2. Senão → fornecedor de quem **mais recebeu nos últimos 6 meses** (maior soma de
   quantidade recebida em unidades nas notas de entrada; empate → o da entrada
   mais recente).
3. Sem entrada nos 6 meses → fornecedor da **negociação alterada por último**.
4. Sem negociação e sem entrada → grupo **SEM FORNECEDOR** (fim da barra).

## Regra 2 — estoque mínimo (mediana de janelas rolantes)

1. Vendas diárias em **unidades** dos últimos **180 dias** (`tbVendaPDV` via bridge;
   dias sem linha = venda 0).
2. Janela rolante de **45 dias corridos**, deslizando 1 dia por vez → até 136 janelas.
   Cada janela = soma das unidades vendidas nos seus 45 dias.
3. **Ruptura por curva**: descarta a janela que tiver N+ dias SEGUIDOS sem venda,
   com N por curva ABC do produto:
   - curva **A** → 10 dias · curva **B** → 20 dias · curva **C** → 30 dias
   - produto **sem curva** no ERP → 20 dias (igual a B)
4. Janelas anteriores à **primeira venda** do produto no período não contam
   (produto novo não é ruptura).
5. **Estoque mínimo = mediana** das somas das janelas limpas.
6. Casos-limite:
   - **Nenhuma janela limpa** → mediana de TODAS as janelas (com ruptura), linha
     marcada com `*` ("calculado com ruptura — pode estar subestimado").
   - **Produto novo** (primeira venda há menos de 45 dias) → estimativa proporcional:
     média diária desde a primeira venda × 45, linha marcada "novo".
   - **Sem venda nenhuma nos 180 dias** → célula "—" com etiqueta "sem venda 6m"
     (não há o que estimar).
7. **Conversão para caixa-mãe**: divide pela embalagem da maior caixa do catálogo
   (`QUANTIDADE_CAIXA`) e arredonda **para cima** → "7 cx". Produto sem caixa-mãe
   (embalagem ≤ 1) → em unidades ("40 un"). Item de balança (kg) → em kg, teto ("12 kg").

## Layout do HTML

- **Barra do topo**: campo de busca (filtra enquanto digita) + lista de fornecedores
  com contagem de produtos. **COTACAO fixo em primeiro** (é o maior grupo), demais em
  ordem alfabética, **SEM FORNECEDOR por último**. Só aparecem fornecedores com ≥ 1
  produto ativo atribuído.
- **Tabela do fornecedor**: código · produto · curva · corredor · est. mínimo.
  Ordenada por **corredor** (A1→A25; sem rua vai para o fim), depois por nome —
  para conferir andando pelas ruas do depósito.
- Marcas nas linhas: `*` (só janelas com ruptura) e `novo` (estimativa proporcional).
- Legenda das marcas no rodapé. Mobile-first (mesmo estilo dos outros apps do ponte).

## Dados novos que o bridge precisa exportar

| arquivo | conteúdo | fonte |
|---------|----------|-------|
| negociação | produto × fornecedor × dtAlteracao (inclui flag "é COTACAO") | `tbNegociacao` + `tbPessoa` (via `tbProduto.cdSuperProduto`) |
| entradas 6m | produto × fornecedor × quantidade em UNIDADES (volumes × embalagem da nota) × data | notas de entrada (`tbNota`/itens, `cdPessoaComercial`) |
| vendas 180d | produto × dia × unidades | export DEDICADO com a query `VENDAS` e janela fixa de 180 dias (a `janela_dias` global do ponte é 120 e alimenta os detectores — não mexer nela) |

Catálogo (código, nome, embalagem, curva, peso/balança, ativo) já existe.
Corredor: ler o `estado_json` do `deposito-atacaderj` no ponte (só leitura).

## Testes (pytest, dados sintéticos)

- Atribuição de fornecedor: COTACAO vence; maior recebimento 6m; empate → mais
  recente; fallback negociação; SEM FORNECEDOR.
- Janelas: contagem (180d → 136), soma, descarte por ruptura com N por curva
  (A=10/B=20/C=30/sem=20), janelas pré-primeira-venda fora.
- Mediana par/ímpar; fallback todas-com-ruptura marca `*`; produto novo (média×45,
  marca "novo"); sem venda → "—".
- Conversão: teto em cx; sem caixa → un; balança → kg.
- Ordenação da tabela (corredor→nome) e da barra (COTACAO primeiro, SEM FORNECEDOR último).

## Fora de escopo (por enquanto)

- Tarefa agendada (aguardando validação do dono).
- Envio por WhatsApp (o visualizador não executa JavaScript — armadilha conhecida).
- Impressão caprichada / exportar planilha.

## Decisões do dono (22/07/2026)

- Fornecedor: campo da NEGOCIAÇÃO; "COTACAO" é exclusivo; senão o mais recebido em 6m.
- Histórico das janelas: **6 meses**.
- Sem janela limpa → usar as janelas com ruptura (com marca).
- Ruptura por curva: A=10, B=20, C=30 dias seguidos sem venda.
- Formato: relatório HTML estático, aberto no navegador direto.
- Sem agendamento por enquanto — só teste manual.
