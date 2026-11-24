#!/bin/sh
# Subida da API no Render (render.yaml): prepara o banco e inicia o servidor.
# Os três passos são idempotentes: rodar a cada deploy não duplica nada.
set -e
alembic upgrade head                      # cria/atualiza as tabelas
python -m app.modules.stories.seed        # carrega as três histórias de exemplo
python -m app.modules.stories.annotate    # phrasal verbs e palavras difíceis de cada frase
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
