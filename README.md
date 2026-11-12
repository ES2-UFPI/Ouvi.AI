# Ouvi.AI

[![CI](https://github.com/ES2-UFPI/Ouvi.AI/actions/workflows/ci.yml/badge.svg)](https://github.com/ES2-UFPI/Ouvi.AI/actions/workflows/ci.yml)

Plataforma de streaming de áudio para aprendizado de idiomas, com alternância
fluida entre Português e Inglês na mesma faixa, mantendo a mesma voz do
narrador.

## Arquitetura

- **Frontend:** React + Vite + TypeScript + Tailwind (SPA)
- **Backend:** FastAPI (monólito modular, em camadas Router → Service → Repository)
- **Banco de dados:** PostgreSQL
- **Armazenamento de arquivos:** MinIO (compatível com S3)

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e aberto
- Git
- [Node.js](https://nodejs.org/) 22.12 ou mais novo (recomendado: 24), para rodar o frontend e os testes dele (o Vitest 5 não funciona com o Node 20)

O backend, o banco e o MinIO rodam dentro do Docker, sem precisar instalar
Python. O frontend roda na sua máquina, com `npm run dev`.

## Configuração inicial

1. Clone o repositório:
```bash
git clone https://github.com/ES2-UFPI/Ouvi.AI.git
cd Ouvi.AI
```

2. Copie os arquivos de variáveis de ambiente de exemplo (opcional para desenvolvimento: sem o `.env` da raiz,
   o `docker-compose.yml` usa os mesmos valores do `.env.example`, então `docker compose up` funciona logo após o clone):
```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

3. Os valores de exemplo já funcionam para desenvolvimento local. Se quiser
   trocá-los, edite o `.env` da raiz (banco e MinIO) e o `backend/.env`.
   Troque o `JWT_SECRET` do `backend/.env` por um valor aleatório:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
   Se não tiver Python instalado, qualquer string aleatória longa serve para
   desenvolvimento local.

## Rodando o projeto

**1. Suba a API, o PostgreSQL e o MinIO:**
```bash
docker compose up -d --build
```

Na primeira vez, o build pode levar alguns minutos (baixando as imagens e
instalando dependências).

**2. Crie as tabelas do banco (migrações):**
```bash
docker compose exec api alembic upgrade head
```
Rode de novo sempre que alguém adicionar uma migração nova.

**3. Carregue as histórias de exemplo** (três fábulas bilíngues, divididas em frases):
```bash
docker compose exec api python -m app.modules.stories.seed
```
Pode rodar quantas vezes quiser: não duplica nada. Opções: `--dry-run` (mostra o que faria, sem gravar),
`--check` (só valida os arquivos JSON, sem banco) e `--prune` (remove do banco frases além do fim de cada JSON).
Os textos e a origem de cada um estão em `backend/app/modules/stories/seed/`.

**4. Anote as histórias** (acha os phrasal verbs de cada frase e o equivalente em português):
```bash
docker compose exec api python -m app.modules.stories.annotate
```
Pode rodar quantas vezes quiser: as anotações antigas são substituídas, sem duplicar nada. Opções: `--story-id N`
(anota só uma história) e `--dry-run` (mostra o que faria, sem gravar). Ao final o comando mostra as contagens e
lista os trechos que ficaram sem equivalente em português.

**5. Suba o frontend**, em outro terminal:
```bash
cd frontend
npm install
npm run dev
```

Pronto. Acesse:

| Serviço | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| API (Swagger) | http://localhost:8000/docs |
| Health check da API | http://localhost:8000/health |
| Console do MinIO | http://localhost:9001 |

Para parar os containers:
```bash
docker compose down
```

Para parar e apagar os dados do banco/MinIO (começar do zero):
```bash
docker compose down -v
```

## Detector de phrasal verbs (NLP)

O backend usa o [spaCy](https://spacy.io/) com o modelo `en_core_web_sm` para achar phrasal verbs em textos em
inglês (código em `backend/app/modules/stories/nlp/`). Para experimentar:

```bash
docker compose exec api python -c "from app.modules.stories.nlp.factory import DetectorFactory; print(DetectorFactory.create('phrasal_verb').detect('She turned the light off.'))"
```

Os phrasal verbs aceitos ficam em `nlp/data/phrasal_verbs.txt`, um por linha. Para aceitar mais um, basta
acrescentar uma linha.

**Impacto no build da imagem da API** (medido sem cache do Docker, em Windows com Docker Desktop; os números
variam conforme a máquina e a internet):

| | Tempo do build | Tamanho da imagem |
|---|---|---|
| Antes (sem spaCy) | cerca de 20 s | 332 MB |
| Depois (com spaCy e o modelo) | cerca de 46 s | 749 MB |

O modelo é instalado pelo `requirements.txt`. Com o cache do Docker, rebuilds em que o `requirements.txt` não mudou
continuam rápidos. O modelo é carregado uma única vez por processo, na primeira vez que um detector é criado, então a
subida da API não fica mais lenta.

> O `requirements.txt` fixa `preshed==3.0.9` de propósito: a versão 3.0.14 impede o spaCy de carregar o modelo
> (`OverflowError`). Antes de atualizar o spaCy ou o `preshed`, rode os testes.

## Alinhamento português/inglês

Para trocar um trecho de idioma no áudio, é preciso saber onde está o equivalente em português. O `TextAnnotator`
(`backend/app/modules/stories/annotator.py`) roda o detector em cada frase em inglês e procura o equivalente na frase
em português com um dicionário curado: `backend/app/modules/stories/nlp/data/pt_equivalents.json`.

Cada entrada liga um phrasal verb às formas dele em português:

```json
"give up": ["desistir", "desistiu", "desistiram", "desistindo"],
"leave behind": ["deixou ... para trás", "deixaram ... para trás"]
```

- A busca ignora maiúsculas e acentos, respeita limites de palavra e, se a forma aparece mais de uma vez, escolhe a
  ocorrência mais próxima da posição do trecho em inglês.
- `...` vale de 1 a 4 palavras no meio (para phrasal verbs separáveis, como *deixou **a tartaruga** para trás*).
- A forma em português deve cobrir os mesmos pedaços que o trecho em inglês. O detector acha *chase me away*, sem o
  sujeito, então a forma é `me expulsem` e não `eles me expulsem`.
- Trecho sem entrada no dicionário não se perde: fica gravado com os campos `pt_*` nulos e aparece no relatório do
  comando de anotação. Acrescente as formas e rode o comando de novo.

## Trechos candidatos pela API

`GET /stories/{id}/segments` (exige token) devolve as frases da história em ordem de `position`, cada uma com suas anotações em ordem de `en_start`.

| Parâmetro | Efeito |
|---|---|
| `kind=phrasal_verb` | só anotações desse tipo (outro valor responde `422`) |
| `aligned_only=true` | só anotações que já têm equivalente em português |

Erros: `404` história inexistente, `401` sem token, `422` filtro inválido. Sem paginação (as histórias têm algumas dezenas de frases). O número de consultas ao banco é fixo (história, frases e anotações), não importa quantas frases existam. Outros módulos devem usar `StoryService.get_segments`, nunca o repositório.

## Armazenamento de arquivos (S3)

Áudios e outros arquivos ficam num armazenamento de objetos compatível com S3: MinIO em desenvolvimento,
Cloudflare R2 em produção. O código usa sempre a interface `ObjectStorage` (`app/integrations/storage`),
recebida pela dependência `Depends(get_storage)`. Nenhum outro módulo importa o `boto3`.

| Variável (`backend/.env`) | Para que serve |
|---|---|
| `STORAGE_BACKEND` | `s3` (MinIO/R2) ou `memory` (dicionário em memória, para testes) |
| `STORAGE_ENDPOINT` | endpoint que a API usa (`http://minio:9000` dentro do Docker) |
| `STORAGE_PUBLIC_ENDPOINT` | endpoint que o navegador usa nas URLs assinadas (`http://localhost:9000` em dev) |
| `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` | credenciais; no Docker vêm do `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` da raiz |
| `STORAGE_BUCKET` | nome do bucket (padrão `ouveai-audio`) |
| `STORAGE_REGION` | região; o MinIO aceita qualquer uma, o R2 usa `auto` |
| `APP_ENV` | com `development`, a API cria o bucket sozinha na subida |

Para testar o player antes de existir TTS, envie um áudio de exemplo. O script imprime a chave gravada e
uma URL assinada que abre direto no navegador:

```bash
docker compose exec api python -m scripts.upload_sample_audio                  # gera um tom de 30 s
docker compose exec api python -m scripts.upload_sample_audio caminho/do.mp3   # envia um arquivo seu
docker compose exec api python -m scripts.upload_sample_audio --story 1 --story 2   # áudio das histórias 1 e 2
```

O player da página `/player/<id da história>` pede o áudio na chave `stories/<id>/audio.wav`. Com `--story` o
script grava o tom de exemplo nessa chave (ou um `.wav` seu, se você informar o caminho). Uma história sem áudio
mostra "O áudio desta história ainda não foi gerado." no player.

## Streaming de áudio

A tag `<audio>` do navegador não envia o header `Authorization`, então o áudio é entregue por uma URL
assinada (HMAC-SHA256) de curta duração, em duas etapas:

1. O front chama `GET /audio/url?key=<chave>` **com o token** e recebe `{"url": ..., "expires_at": ...}`.
2. O front põe essa `url` no `src` do `<audio>`. Ela aponta para `GET /audio/stream`, que **não exige token**:
   a assinatura basta.

`GET /audio/stream` suporta o header `Range`, para o player pular para o meio sem baixar o arquivo todo:

| Requisição | Resposta |
|---|---|
| sem `Range` | `200` com o arquivo inteiro |
| `Range: bytes=0-99`, `bytes=500-` ou `bytes=-200` | `206` com o trecho e o `Content-Range` |
| faixa inválida ou fora do arquivo | `416` com `Content-Range: bytes */<tamanho>` |
| assinatura adulterada ou URL expirada | `403` |
| chave inexistente | `404` |

| Variável (`backend/.env`) | Para que serve |
|---|---|
| `AUDIO_SIGNING_SECRET` | segredo das assinaturas; use um valor aleatório, diferente do `JWT_SECRET` |
| `AUDIO_URL_TTL_SECONDS` | validade da URL, em segundos (padrão `3600`) |

Para testar com `curl`, gere uma URL em `GET /audio/url` (pelo `/docs`, depois do **Authorize**) e rode:

```bash
curl -s -o /dev/null -D - -H "Range: bytes=0-99" "<url>"
```

## Provedor de TTS (síntese de voz)

A voz é gerada por um provedor de TTS escolhido por configuração. O código usa sempre a interface `TTSProvider`
(`app/integrations/tts`), recebida pela dependência `Depends(get_tts_provider)`, então trocar de fornecedor não mexe
no resto do sistema. Nenhum módulo fala direto com o fornecedor.

| Variável (`backend/.env`) | Para que serve |
|---|---|
| `TTS_PROVIDER` | `fake` (padrão): gera tons, sem rede e sem chave. `azure`: voz real do Azure Speech. Um valor desconhecido **derruba a API na subida**, com a lista dos que existem |
| `TTS_API_KEY` | chave do fornecedor real (o provedor falso ignora). Nunca vai para o repositório |
| `TTS_REGION` | região do serviço do fornecedor real (no Azure, ex.: `brazilsouth`, `eastus`) |
| `TTS_VOICE_ID` | voz usada na síntese (no Azure, o nome da voz, ex.: `pt-BR-ThalitaMultilingualNeural`) |

Um clone novo sobe com `TTS_PROVIDER=fake`, sem nenhuma chave.

**O provedor falso é audível.** Ele lê o SSML e, para cada pedaço de texto, gera um tom de 60 ms por caractere: o
idioma base do `<speak>` soa como um tom **grave** (330 Hz) e um trecho em outro idioma (`<lang xml:lang="en-US">`)
como um tom **agudo** (660 Hz). Assim a troca de idioma já pode ser ouvida sem TTS real. As tags não contam na duração.
Ele também guarda as chamadas recebidas em `calls`, para os testes conferirem o SSML enviado.

```python
from app.integrations.tts import FakeTTSProvider

fake = FakeTTSProvider()
resultado = fake.synthesize(
    '<speak xml:lang="pt-BR">A raposa <lang xml:lang="en-US">gave up</lang> das uvas.</speak>', "qualquer-voz"
)
resultado.format       # "wav"
resultado.duration_ms  # 60 ms por caractere de texto (sem as tags)
fake.calls             # [FakeCall(ssml=..., voice_id="qualquer-voz")]
```

Nos testes, troque o provedor com `app.dependency_overrides[get_tts_provider] = lambda: FakeTTSProvider()`.
Um erro de síntese é um `TTSError`, com `retryable` dizendo se vale tentar de novo.

### TTS real (Azure Speech)

O `AzureTTSAdapter` (`app/integrations/tts/azure.py`) chama a API REST do Azure Speech com `httpx` e devolve um MP3
(24 kHz, 48 kbit/s, mono). A troca de idioma é feita pelo próprio SSML: o trecho em `<lang xml:lang="en-US">` é falado
em inglês **com a mesma voz**, desde que a voz seja *multilíngue* (com `Multilingual` no nome). O adaptador põe a voz
no SSML (`<voice name="...">`), então o compositor não precisa saber qual é.

1. No [portal do Azure](https://portal.azure.com), crie um recurso **Speech** (o plano gratuito F0 serve; com o
   Azure for Students não precisa de cartão).
2. Em **Chaves e ponto de extremidade**, copie a **Chave 1** e a **Região**.
3. No `backend/.env` (que não vai para o repositório):

   ```
   TTS_PROVIDER=azure
   TTS_API_KEY=<a chave>
   TTS_REGION=<a região, ex.: brazilsouth>
   TTS_VOICE_ID=pt-BR-ThalitaMultilingualNeural
   ```

4. Reinicie a API. Sem `TTS_API_KEY` ou `TTS_REGION`, ou com a voz do provedor falso (`fake-voice`), a API não sobe
   e diz qual variável falta.

**Trocar a voz** é só mudar `TTS_VOICE_ID`, sem mexer em código. Candidatas multilíngues: `pt-BR-ThalitaMultilingualNeural`,
`en-US-AvaMultilingualNeural` e `en-US-AndrewMultilingualNeural` (a lista completa está na
[documentação do Azure](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts)).
A comparação entre elas e a voz escolhida estão em [`docs/poc-tts.md`](docs/poc-tts.md).

**Erros e novas tentativas.** Respostas `429` e `5xx`, tempo esgotado (10 s) e falhas de rede são tentados de novo
até 3 vezes, com espera crescente (0,5 s, 1 s, 2 s, ou o `Retry-After` do Azure); depois vem um
`TTSError(retryable=True)`. `400` (SSML recusado) e `401`/`403` (chave) levantam `TTSError(retryable=False)` na hora.
A chave nunca aparece em mensagens de erro, logs nem no `repr` do adaptador.

**Teste com o Azure de verdade.** Os testes normais simulam o Azure e rodam sem rede. O teste manual sintetiza uma
frase com troca de idioma, confere a duração e salva o MP3 para ouvir. Ele só roda com a chave no `backend/.env`
(sem ela, aparece como pulado). Na pasta `backend`:

```
.\venv\Scripts\python.exe -m pytest -m tts_real -s

## Composição do áudio (AudioComposer)

O `AudioComposer` (`backend/app/modules/audio/composer/`) decide **o que muda de idioma** em cada frase e monta o texto
com marcação SSML que vai ao TTS. Ele não usa rede, banco nem TTS: recebe frases e anotações e devolve texto, por isso é
fácil de testar.

```python
from app.modules.audio.composer import AudioComposer

composer = AudioComposer()
# 1) escolhe os trechos trocados na HISTÓRIA INTEIRA (o que a densidade do filtro pede)
selected = composer.select_swaps(segments, ["phrasal_verbs"], "medium")
# 2) compõe cada frase
composed = composer.compose(segment, selected, "pt")
composed.ssml   # <speak version="1.0" xml:lang="pt-BR">A raposa <lang xml:lang="en-US">gave up</lang> das uvas.</speak>
composed.text   # "A raposa desistiu das uvas."  (o texto que aparece na tela, sem marcação)
composed.swaps  # [Swap(start=9, end=17, text="desistiu", spoken="gave up", lang="en-US", annotation_id=1)]
```

**Densidade.** É a fração dos phrasal verbs **da história inteira** (e não por frase) que muda de idioma:

| Densidade | Fração trocada | Exemplo, história com 20 trechos |
|---|---|---|
| `low` (baixa) | 15% | 3 trechos |
| `medium` (média) | 35% | 7 trechos |
| `high` (alta) | 60% | 12 trechos |

As frações são constantes (`DENSITY_SHARE`, em `density.py`). Só entram os trechos que **têm equivalente em português**
(o campo `pt_*` preenchido), e só eles contam na fração.

**Determinismo.** A escolha não usa sorteio: os trechos escolhidos ficam no meio de faixas iguais da história (o 1º, o 4º, o 7º...,
espaçados de forma regular). O mesmo filtro e a mesma história geram sempre o mesmo SSML, o que o cache de áudio exige.

**Direção.** Com `base_language="pt"` o português fica na tela e os trechos são falados em inglês (`en-US`). Com `"en"` é o
inverso (os trechos são falados em `pt-BR`). O `Swap` informa as posições no texto exibido, para o front destacar o trecho.

**Novos tipos de trecho.** O filtro usa `phrasal_verbs` (plural) e a anotação usa `phrasal_verb` (singular): a `SwapStrategyFactory`
liga um ao outro. Um tipo novo entra com uma `SwapStrategy` e uma linha na fábrica.

Para **ver** a composição das histórias reais (precisa do seed e da anotação), sem escrever código:

```bash
docker compose exec api python -m scripts.compose_demo --density high
docker compose exec api python -m scripts.compose_demo --story 2 --density low --ssml
```

## Filtro de Audição e player (front)

1. Em `/filter`, escolha a história, o idioma base, o tipo de trecho e a densidade, e clique em **Salvar filtro**.
   O botão fica desativado até haver idioma base e pelo menos um tipo de trecho. O filtro é gravado em `/filters`,
   vinculado ao seu usuário, e reaparece preenchido ao reabrir a tela (um filtro por história).
2. Com o filtro salvo, **Ouvir** leva a `/player/<história>?filter=<id>`. O player pede a URL assinada em
   `GET /audio/url` e toca com a tag `<audio>`: pular na barra usa HTTP Range. Há play/pausa, voltar e avançar 15 s,
   velocidades de 0,75x a 2x (sem mudar o tom da voz), tempo atual e duração, indicador de carregamento e mensagem
   de erro.

## Testes e integração contínua

### Rodando os testes

**Backend** (pytest, dentro do container):

```bash
docker compose exec api pip install -r requirements-dev.txt
docker compose exec api python -m pytest
docker compose exec api python -m pytest --cov=app --cov-report=term-missing:skip-covered   # com cobertura
```

- Os testes que usam o banco rodam numa transação que é desfeita no final: não alteram os dados do seu ambiente.
  Eles precisam do Postgres no ar e migrado (`alembic upgrade head`); **localmente** sem isso são pulados, e **na CI** a
  suíte falha (senão ficaria verde sem testar nada).
- O `pip install` precisa ser repetido se o container for recriado (`docker compose up --build`).
- Os testes de armazenamento rodam na `InMemoryStorage` sempre e no MinIO quando ele está no ar; sem ele, a parte S3 é pulada.
- Os testes de API usam a fixture `api` (cliente HTTP com a autenticação **real**) e `make_user` (cria um usuário pela
  própria API), definidas em `backend/tests/conftest.py`.

**Frontend** (Vitest + Testing Library):

```bash
cd frontend
npm run test:run     # uma vez
npm test             # modo observação, reroda ao salvar
```

### Integração contínua (GitHub Actions)

O workflow `.github/workflows/ci.yml` roda a cada pull request e a cada push na `develop` e na `main`:

| Job | O que faz |
|---|---|
| Backend | PostgreSQL 16 de serviço, `alembic upgrade head`, `pytest` com cobertura e **falha se a cobertura ficar abaixo de 80%** |
| Frontend | `npm ci`, `npm run lint`, `npm run build` (tipos + empacotamento) e `npm run test:run` |

Regra da equipe: **um PR só é mergeado com os dois jobs verdes** (confira a aba *Checks* do PR). Para reproduzir a CI
na sua máquina, rode os comandos acima antes de abrir o PR.

### Proteção da `develop` e da `main`

O ruleset **"Regras de Merge"** (*Settings > Rules > Rulesets*) vale para a `develop` e para a `main`, sem exceções
(nem para administradores):

- **Só por pull request, com 1 aprovação de outra pessoa.** Push direto na branch é recusado, e o GitHub não deixa
  aprovar o próprio PR. Peça a revisão em *Reviewers* ao abrir o PR.
- **Não é possível apagar a branch nem fazer force push.**

Fluxo: o autor abre o PR, outra pessoa revisa e aprova, e o **autor** faz o merge. Os jobs verdes da CI continuam sendo
regra da equipe, mas não bloqueiam o merge no GitHub: confira antes de mergear.

### TDD: como escrevemos código novo

Funcionalidade nova entra pelo teste, na ordem **vermelho → verde → refatorar**:

1. **Vermelho:** escreva o teste do critério de aceite da issue e rode: ele deve **falhar** (prova que o teste enxerga a falta).
2. **Verde:** escreva o mínimo de código para o teste passar.
3. **Refatorar:** limpe o código com a suíte verde, e só então abra o PR.

Boas práticas do projeto:

- Cada critério de aceite da issue vira pelo menos um teste (o nome do teste diz o que ele garante).
- Teste o erro também: `401`, `404`, `409` e `422`, não só o caminho feliz.
- Nada de rede, de chave de API paga nem de MinIO nos testes: use o `FakeTTSProvider` e a `InMemoryStorage`.
- Para duvidar de um teste, estrague o código de propósito (por exemplo, troque um `409` por `400`) e veja se ele falha.
- Código que só existe para a CI passar não vale: se a cobertura cair, escreva o teste que falta.

## Rodando a API sem Docker

Útil para debugar com mais velocidade. O PostgreSQL ainda precisa estar de pé
(`docker compose up -d db`).

```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```
> Fora do Docker a API usa o `DATABASE_URL` e o `STORAGE_ENDPOINT` do
> `backend/.env`, que apontam para `localhost`. Dentro do Docker, o
> `docker-compose.yml` troca esses hosts por `db` e `minio` automaticamente.

## Problemas comuns

- **`pull access denied for minio/minio`**: a imagem oficial do MinIO não está
  mais disponível no Docker Hub. O projeto usa `bitnamilegacy/minio` como
  alternativa — se esse erro aparecer, confirme que você tem a versão mais
  recente do `docker-compose.yml`.
- **MinIO falha com `file access denied`**: geralmente acontece quando o
  volume de dados já existia de uma versão anterior. Rode
  `docker compose down -v` para recriar os volumes do zero.
- **A API não conecta ao banco depois de trocar usuário ou senha no `.env`**:
  o Postgres só lê essas variáveis na primeira criação do volume. Rode
  `docker compose down -v` e suba de novo.
- **O frontend mostra erro de rede ao entrar ou cadastrar**: confirme que a
  API está de pé (`http://localhost:8000/health`) e que a porta do frontend
  está em `CORS_ORIGINS` no `backend/.env` (padrão: `http://localhost:5173`).

## Estrutura do repositório

```
.
├── backend/              API FastAPI
│   ├── app/
│   │   ├── core/         configurações, banco de dados e segurança (JWT, hash)
│   │   ├── integrations/ adaptadores de serviços externos (TTS, NLP, S3)
│   │   └── modules/      módulos de negócio: auth, users, filters, stories, audio, health
│   ├── alembic/          migrações do banco
│   ├── scripts/          scripts de apoio (ex.: enviar áudio de exemplo ao MinIO)
│   └── Dockerfile
├── frontend/             SPA React (código organizado por feature)
├── docker-compose.yml    API, PostgreSQL e MinIO
└── .env.example          variáveis de ambiente de exemplo
```

Cada módulo do backend segue as camadas `router.py` (HTTP), `service.py`
(regras de negócio), `repository.py` (acesso a dados) e `schemas.py`
(entrada e saída da API).
