"""Detecção de trechos candidatos à troca de idioma (NLP).

Cada tipo de trecho (phrasal verbs, palavras difíceis...) é um detector que segue a interface
`AnnotationDetector` (padrão Strategy). A `DetectorFactory` escolhe o detector pelo tipo.

Este `__init__` é leve de propósito: o spaCy só é carregado quando um detector é criado.
"""
