# Pipeline de áudio: como funciona e o que decidimos

Este documento descreve o que foi **realmente construído** na Sprint 2 (US07 e US08) e registra as decisões que
mudaram em relação ao planejamento original, com o motivo. O passo a passo para rodar está no
[README](../README.md); a visão de arquitetura está na wiki do projeto.

## Visão geral

```
frases anotadas ──► AudioComposer ──► SSML ──► cache (AudioBlob) ──acerto──► arquivo já pronto
(Segment + Annotation)                          │ erro
                                                ▼
                                        TTSProvider ──► ObjectStorage ──► AudioAsset (ready)
```

| Etapa | Onde | Papel |
|---|---|---|
| Anotação | `app/modules/stories/` | acha os phrasal verbs e o equivalente em português (`Segment`, `Annotation`) |
| Seleção e composição | `app/modules/audio/composer/` | escolhe quais trechos trocar (densidade) e monta o SSML da frase |
| Prévia | `app/modules/audio/preview_*` | mostra no texto o que será trocado, sem gerar áudio nem gastar TTS |
| Síntese | `app/integrations/tts/` | `TTSProvider` (Adapter): `FakeTTSProvider` agora, Azure depois |
| Armazenamento | `app/integrations/storage/` | `ObjectStorage` (Adapter): MinIO/R2 em produção, memória nos testes |
| Cache | `app/modules/audio/cache/` | `AudioBlob`: o mesmo conteúdo nunca é sintetizado duas vezes |
| Orquestração | `app/modules/audio/facade.py` | `AudioGenerationFacade.generate()` junta tudo, frase a frase |
| API | `app/modules/audio/generation_router.py` | gera em segundo plano, status por polling, URL assinada |
| Entrega | `app/modules/audio/router.py` | `GET /audio/stream` com HTTP Range |

## Modelos como foram implementados

**`Segment`** (`segments`): uma frase da história. `position`, `text_en`, `text_pt`.

**`Annotation`** (`annotations`): um trecho anotado de uma frase. `kind` (tipo, ex.: `phrasal_verb`), `lemma`, posições
no texto em inglês (`en_start`, `en_end`, `en_text`) e, quando há equivalente, no português (`pt_start`, `pt_end`,
`pt_text`). Sem equivalente em português, as colunas `pt_*` ficam nulas e o trecho **nunca** vira troca.

**`AudioAsset`** (`audio_assets`): o áudio de **uma frase** com **um filtro**. Único por
`(segment_id, rules_hash, voice_id)`. `status` é `pending`, `generating`, `ready` ou `failed`; guarda `storage_key`,
`format`, `duration_ms`, `error`, `attempts` e o `blob_id` do cache. `rules_hash` é o SHA-256 das regras do filtro:
filtros com as mesmas regras compartilham o registro.

**`AudioBlob`** (`audio_blobs`): o arquivo sintetizado, identificado por `cache_key` (SHA-256 do SSML + voz + fornecedor
+ formato). Guarda `storage_key`, `format`, `duration_ms`, `size_bytes`, `char_count`, `hit_count` e `miss_count`.

## Endpoints

Todas as rotas de geração exigem `Authorization: Bearer <token>`. Filtro inexistente ou de outro usuário responde
`404`; filtro de outra história ou com regras inválidas, `422`.

### `GET /stories/{story_id}/preview?filter_id=3`

O texto com as trocas já calculadas, sem gerar áudio.

```json
{
  "story": {"id": 1, "title": "A raposa e as uvas", "language": "en"},
  "rules": {"base_language": "pt", "segment_types": ["phrasal_verbs"], "density": "high"},
  "totals": {"segments": 12, "candidates": 9, "swapped": 5},
  "density_profile": [
    {"segment_id": 7, "position": 0, "candidates": 1, "swapped": 1, "target": 0.6}
  ],
  "segments": [
    {"id": 7, "position": 0, "text": "Ela desistiu da corrida.",
     "swaps": [{"start": 4, "end": 12, "text": "desistiu", "spoken": "gave up", "lang": "en-US", "annotation_id": 21}]}
  ]
}
```

`density_profile` traz, para cada frase (em ordem), os candidatos, as trocas feitas (o mesmo que `len(swaps)`) e
a fração-alvo `target` (0 a 1). Na densidade fixa (Cenários A e B), `target` é igual em todas as frases; no Cenário C
ele segue a curva crescente (veja abaixo). O player desenha a faixa de densidade com ele.

### Cenário C: densidade crescente (US11)

Filtro: `{"base_language": "pt", "segment_types": ["advanced_vocabulary"], "density": "medium", "progression": "increasing"}`.
O vocabulário avançado são as palavras difíceis de nível `advanced` com equivalente alinhado em português; o texto e a
narração ficam em português, e a palavra é falada em inglês (`<lang xml:lang="en-US">`) pela mesma voz.

- `progression`: `fixed` (padrão, Cenários A e B; fica fora das regras salvas, então o hash dos filtros antigos não
  muda) ou `increasing` (obrigatória no Cenário C). Os Cenários A e C têm a mesma base, mas não se misturam no mesmo
  filtro.
- A curva (`DensityCurve`, em `app/modules/audio/composer/density.py`) dá a fração-alvo de cada frase: a frase `i` de
  `n` fica na posição `x = (i + 0,5) / n` e tem alvo `final x (1 + 4x) / 5`, ou seja, 20% da densidade final no começo
  subindo em linha reta até ela no fim. A `density` do filtro é a densidade **final**.
- A seleção usa o método do **acumulador**: cada candidato soma o alvo da sua frase e é trocado quando o acumulado passa
  de uma troca inteira (começando em meia troca). Até qualquer ponto da história, o número de trocas é a soma da curva
  arredondada; é determinístico e feito só com inteiros, e o front (`swaps.ts`) repete a mesma conta.

### `POST /stories/{story_id}/audio`

Corpo: `{"filter_id": 3}`. Responde `202` na hora e gera em segundo plano. Pedir de novo durante a geração não dispara
outra (`202`); com tudo pronto responde `200`; frases que falharam são tentadas de novo.

```json
{
  "story_id": 1, "filter_id": 3, "state": "generating", "total": 12, "ready": 5, "failed": 0,
  "segments": [{"segment_id": 7, "position": 0, "status": "ready", "duration_ms": 2340, "error": null}]
}
```

### `GET /stories/{story_id}/audio/status?filter_id=3`

Mesma resposta do `POST`, para o front consultar por polling. `state`: `pending`, `generating`, `ready` ou `failed`.

### `GET /audio/segments/{segment_id}?filter_id=3`

```json
{"url": "http://localhost:8000/audio/stream?key=cache%2F5e%2F5ee0d2....wav&expires=1790000000&signature=...",
 "expires_at": "2026-11-12T15:00:00Z", "segment_id": 7, "duration_ms": 2340, "format": "wav"}
```

`409` se o áudio da frase ainda não está pronto ou se a geração dele falhou.

### `GET /stories/{story_id}/audio/full?filter_id=3`

O **áudio único** da história: todas as frases prontas num arquivo só, para o player tocar de uma vez e
voltar a qualquer palavra. O arquivo é montado na primeira chamada (MP3 de taxa constante: os quadros são
colados em ordem; WAV: cabeçalho novo) e guardado no armazenamento com o hash das chaves das frases, então é
reaproveitado enquanto nenhuma frase mudar.

```json
{"url": "http://localhost:8000/audio/stream?key=full%2F5fe98e....mp3&expires=1790000000&signature=...",
 "expires_at": "2026-11-12T15:00:00Z", "duration_ms": 53424, "format": "mp3", "skipped": [],
 "segments": [{"segment_id": 7, "position": 0, "start_ms": 0, "duration_ms": 4680},
              {"segment_id": 8, "position": 1, "start_ms": 4680, "duration_ms": 4944}]}
```

`409` se alguma frase ainda não terminou de ser gerada ou se nenhuma ficou pronta. As frases que falharam ficam
de fora do arquivo e vêm em `skipped` (sem buraco na linha do tempo). A URL é a do `GET /audio/stream`, com Range.

### `GET /audio/stream?key=...&expires=...&signature=...`

Sem token (a tag `<audio>` não envia `Authorization`): o acesso é garantido pela assinatura. Aceita `Range`
(`206` com `Content-Range`); assinatura adulterada ou URL vencida responde `403`.

## Sequência: gerar e tocar

```
Player          API (router)       Facade (segundo plano)        TTS / Storage
  │  POST /audio    │                       │                          │
  │────────────────►│ cria AudioAssets      │                          │
  │◄── 202 + status │ agenda a tarefa ─────►│ por frase: compõe SSML   │
  │                 │                       │ cache? ─ não ───────────►│ sintetiza e grava
  │  GET /status    │                       │ marca a frase `ready`    │
  │────────────────►│ (polling)             │                          │
  │◄── 5/12 prontas │                       │                          │
  │  GET /segments/7│                       │                          │
  │────────────────►│ confere a posse do filtro e assina a URL         │
  │◄── URL assinada │                       │                          │
  │  GET /stream (Range)  ──────────────────────────────────────────►│ lê o trecho
```

## Decisões que mudaram em relação ao planejamento

| Planejado | Construído | Motivo |
|---|---|---|
| Gerar o áudio da história e responder quando terminar | `POST` responde `202` e a geração roda em segundo plano; o front acompanha por polling | gerar leva de segundos a minutos; uma requisição presa estouraria o tempo limite |
| Um arquivo de áudio por história | Um `AudioAsset` por **frase** | a primeira frase fica pronta e já toca enquanto as demais são geradas; uma falha afeta só uma frase |
| Autenticar o áudio com o JWT | URL assinada por HMAC com segredo próprio (`AUDIO_SIGNING_SECRET`) | o `<audio>` não manda `Authorization`; segredo separado: trocar um não invalida o outro |
| Front calcula as trocas | O back calcula (`AudioComposer.select_swaps`) e a prévia expõe o resultado | o texto na tela e o áudio nunca divergem: a mesma função decide os dois |
| Escolha aleatória das trocas | Escolha **determinística**, espaçamento uniforme sobre a história inteira (densidade baixa 15%, média 35%, alta 60%) | o mesmo filtro gera sempre o mesmo áudio, o que também viabiliza o cache e os testes |
| Cache por usuário ou por filtro | Cache **global** por conteúdo (SSML + voz + fornecedor + formato) | filtros e usuários diferentes com a mesma frase falada reaproveitam o arquivo e economizam TTS |
| Começar direto com a voz real | `FakeTTSProvider` como padrão: tons de 330 Hz (idioma base) e 660 Hz (trecho trocado), sem rede nem chave | um clone novo sobe sem chave e os testes ficam rápidos; trocar o provedor é só configuração |
| `GET /audio/url` para o player | `GET /audio/segments/{segment_id}`; `/audio/url` ficou só em desenvolvimento | o novo endpoint confere a posse do filtro; o antigo assina qualquer chave |

## Prova de conceito do TTS real (#81)

Feita em 12/11/2026 com o `AzureTTSAdapter` (região `brazilsouth`, três vozes multilíngues). O relatório completo, com a
latência por frase, o custo por 1.000 caracteres (US$ 0,015 no plano pago, zero no F0) e a nota de naturalidade, está em
[`poc-tts.md`](poc-tts.md). Voz padrão: `pt-BR-ThalitaMultilingualNeural`; trocar é só mudar `TTS_VOICE_ID`.
