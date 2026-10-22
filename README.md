# Ouvi.AI

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
- [Node.js](https://nodejs.org/) 20 ou mais novo, para rodar o frontend

O backend, o banco e o MinIO rodam dentro do Docker, sem precisar instalar
Python. O frontend roda na sua máquina, com `npm run dev`.

## Configuração inicial

1. Clone o repositório:
```bash
git clone https://github.com/ES2-UFPI/Ouvi.AI.git
cd Ouvi.AI
```

2. Copie os arquivos de variáveis de ambiente de exemplo:
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

**3. Suba o frontend**, em outro terminal:
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
> Fora do Docker a API usa o `DATABASE_URL` e o `MINIO_ENDPOINT` do
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
│   │   └── modules/      módulos de negócio: auth, users, filters, stories, health
│   ├── alembic/          migrações do banco
│   └── Dockerfile
├── frontend/             SPA React (código organizado por feature)
├── docker-compose.yml    API, PostgreSQL e MinIO
└── .env.example          variáveis de ambiente de exemplo
```

Cada módulo do backend segue as camadas `router.py` (HTTP), `service.py`
(regras de negócio), `repository.py` (acesso a dados) e `schemas.py`
(entrada e saída da API).
