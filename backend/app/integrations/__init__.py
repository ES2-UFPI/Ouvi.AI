"""Camada de integrações externas (TTS, NLP, armazenamento S3).

Cada serviço externo fica atrás de um Adapter, para que o resto do sistema
não dependa de um fornecedor específico.
"""
