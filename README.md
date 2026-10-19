# Ouvi.AI

Plataforma de streaming de áudio para aprendizado de idiomas, com alternância
fluida entre Português e Inglês na mesma faixa, mantendo a mesma voz do
narrador.

## Arquitetura

- **Frontend:** React + Vite + TypeScript + Tailwind (SPA)
- **Backend:** FastAPI (monólito modular, por módulo de domínio)
- **Banco de dados:** PostgreSQL
- **Armazenamento de arquivos:** MinIO (compatível com S3)

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e aberto
- Git

Não é necessário instalar Python ou Node localmente para rodar o projeto —
tudo roda dentro dos containers. Eles só são necessários se você for rodar o
frontend ou o backend fora do Docker (ver seção "Rodando sem Docker").

## Configuração inicial

1. Clone o repositório:
```bash
   git clone <url-do-repositorio>
   cd ouve.ai
```

2. Copie os arquivos de variáveis de ambiente de exemplo:
```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
```

3. Abra os arquivos `.env` criados e preencha os valores (usuário/senha do
   banco, credenciais do MinIO, `JWT_SECRET`). Para gerar um `JWT_SECRET`
   aleatório:
```bash
   python -c "import secrets; print(secrets.token_hex(32))"
```
   Se não tiver Python instalado, qualquer string aleatória longa serve para
   desenvolvimento local.

## Rodando o projeto

```bash
docker compose up -d --build
```

Na primeira vez, o build pode levar alguns minutos (baixando as imagens e
instalando dependências). Depois disso, acesse:

| Serviço | URL |
| --- | --- |
| Frontend | http://localhost:5173 |
| API (docs automáticas) | http://localhost:8000/docs |
| Console do MinIO | http://localhost:9001 |

Para parar os containers:
```bash
docker compose down
```

Para parar e apagar os dados do banco/MinIO (começar do zero):
```bash
docker compose down -v
```

## Rodando sem Docker

Útil para debugar com mais velocidade durante o desenvolvimento.

**Backend:**
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
> Atenção: fora do Docker, troque no seu `backend/.env` local os hosts `db` e
> `minio` por `localhost` (eles só resolvem dentro da rede do Docker).

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Problemas comuns

- **`pull access denied for minio/minio`**: a imagem oficial do MinIO foi
  removida do Docker Hub em setembro de 2026. O projeto já usa
  `bitnamilegacy/minio` como alternativa — se esse erro aparecer, confirme
  que você puxou a versão mais recente do `docker-compose.yml`.
- **MinIO falha com `file access denied`**: geralmente acontece quando o
  volume de dados já existia de uma versão anterior. Rode
  `docker compose down -v` para recriar os volumes do zero.
- **Erro de conexão com o banco**: confirme que o `DATABASE_URL` no
  `backend/.env` usa `db` como host (não `localhost`) quando rodando via
  Docker.

## Estrutura do repositório