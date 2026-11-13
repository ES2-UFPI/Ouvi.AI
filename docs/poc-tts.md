# Prova de conceito do TTS real (#81)

O maior risco técnico do Ouvi.AI é a troca de idioma no meio da frase soar natural, com **a mesma voz** nos dois
idiomas. Esta prova de conceito testa isso no Azure Speech antes de fechar o fornecedor.

## Como foi feita

- **Fornecedor:** Azure Speech, recurso na região `brazilsouth`, API REST chamada pelo `AzureTTSAdapter`
  (`backend/app/integrations/tts/azure.py`), saída MP3 (`audio-24khz-48kbitrate-mono-mp3`).
- **Script:** `backend/scripts/poc_tts.py` (`python -m scripts.poc_tts`, a partir da pasta `backend`). Cada voz
  sintetiza cada frase 3 vezes; a latência é o tempo da requisição completa, do envio do SSML até o MP3 recebido.
- **Vozes:** três vozes multilíngues, que falam português e inglês com o mesmo timbre:
  `pt-BR-ThalitaMultilingualNeural`, `en-US-AvaMultilingualNeural` e `en-US-AndrewMultilingualNeural`.
- **Frases:** no mesmo formato que o compositor de SSML gera (idioma base no `<speak>`, trecho trocado em `<lang>`):

| Frase | Idioma base | Texto |
|---|---|---|
| `curta` | pt-BR | A raposa tentou de novo, mas no fim *gave up* das uvas. |
| `varias-trocas` | pt-BR | Quando o despertador tocou, Ana *woke up*, *turned off* o alarme e foi *pick up* o irmão na escola. |
| `base-ingles` | en-US | The old fisherman was *teimoso* and refused to *desistir* before sunrise. |

## Latência

Mediana de 3 execuções por voz e frase (rodada de 12/11/2026, recurso em `brazilsouth`):

| Voz | Frase | Caract. | Duração do áudio | Latência mediana | Mín–máx |
|---|---|---:|---:|---:|---:|
| pt-BR-ThalitaMultilingualNeural | curta | 53 | 3,8 s | 326 ms | 148–604 ms |
| pt-BR-ThalitaMultilingualNeural | varias-trocas | 93 | 5,6 s | 144 ms | 132–480 ms |
| pt-BR-ThalitaMultilingualNeural | base-ingles | 69 | 4,7 s | 411 ms | 390–553 ms |
| en-US-AvaMultilingualNeural | curta | 53 | 3,7 s | 187 ms | 143–257 ms |
| en-US-AvaMultilingualNeural | varias-trocas | 93 | 5,5 s | 182 ms | 172–202 ms |
| en-US-AvaMultilingualNeural | base-ingles | 69 | 4,8 s | 223 ms | 168–348 ms |
| en-US-AndrewMultilingualNeural | curta | 53 | 4,0 s | 214 ms | 181–526 ms |
| en-US-AndrewMultilingualNeural | varias-trocas | 93 | 6,0 s | 529 ms | 190–869 ms |
| en-US-AndrewMultilingualNeural | base-ingles | 69 | 5,5 s | 187 ms | 182–471 ms |

Mediana por voz, juntando as frases: **Thalita 390 ms**, **Ava 187 ms**, **Andrew 214 ms**. A primeira requisição
de uma sessão pode passar de 2 s (abertura da conexão TLS: numa rodada isolada, a primeira chamada levou 2.036 ms).

Para o Ouvi.AI isso basta: cada segmento da história leva menos de 1 s para sintetizar, e o pipeline gera o áudio em
segundo plano e guarda no cache (US08), então o usuário não espera a síntese na hora de ouvir.

## Custo por 1.000 caracteres

O Azure cobra pelos caracteres de texto do SSML (as tags não contam).

| Plano | Preço | Observação |
|---|---|---|
| F0 (gratuito) | US$ 0 | 500 mil caracteres por mês de vozes neurais |
| S0 (pago, pay-as-you-go) | **US$ 0,015 por 1.000 caracteres** (US$ 15 por 1 milhão) | preço de tabela das vozes neurais padrão; conferir na [página de preços](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/) antes de mudar de plano |

A rodada completa da prova de conceito usou **1.935 caracteres** (cerca de US$ 0,03 no plano pago, zero no F0). Uma
história do catálogo tem por volta de 1.500 a 3.000 caracteres, ou seja, de US$ 0,02 a US$ 0,05 por história no
plano pago, e o cache (US08) garante que cada combinação de história, voz e trocas seja sintetizada uma vez só. O F0
cobre com folga o uso da disciplina. Para o README, `TTS_COST_PER_1K_CHARS=0.015` faz a estimativa de custo evitado
do cache usar esse preço.

## Naturalidade

Cada pessoa ouviu os 9 MP3 gerados (`backend/poc-tts-audios/`, fora do repositório) e deu nota de 1 (robótico, troca
de idioma estranha) a 5 (soa como uma pessoa bilíngue lendo). A nota da voz é a média das três frases.

| Voz | Allyson | Jeovando | Arielly | Média |
|---|:---:|:---:|:---:|:---:|
| pt-BR-ThalitaMultilingualNeural | _ | _ | _ | _ |
| en-US-AvaMultilingualNeural | _ | _ | _ | _ |
| en-US-AndrewMultilingualNeural | _ | _ | _ | _ |

## Teste do adaptador com a chave real

`pytest tests/test_tts_azure.py` com `TTS_PROVIDER=azure` e `TTS_VOICE_ID=pt-BR-ThalitaMultilingualNeural`: os 38
testes passam, inclusive o teste manual `test_manual_sintetiza_uma_frase_com_troca_de_idioma`, que sintetiza uma frase
com troca de idioma, confere que o MP3 é tocável e que `duration_ms` (2.328 ms) bate com a duração real do arquivo.

## Decisão

- **Fornecedor:** Azure Speech. A troca de idioma com a mesma voz funciona via `<lang xml:lang>`, a latência é baixa e
  o plano gratuito cobre o projeto.
- **Voz padrão:** `pt-BR-ThalitaMultilingualNeural`, porque o público principal tem o português como idioma base (cenários
  A e C). _Confirmar com a média de naturalidade acima._
- **Trocar a voz** é só mudar `TTS_VOICE_ID` no `backend/.env`, sem mexer em código (ver README, seção "TTS real").
