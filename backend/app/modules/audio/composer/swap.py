"""Resultado da composição: o texto exibido, o SSML falado e as trocas de idioma aplicadas."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Swap:
    """Um trecho que muda de idioma na fala, localizado no texto que aparece na tela.

    Serve ao front para destacar o trecho: `texto[start:end] == text`. O idioma base fica na tela, e o
    trecho é FALADO no outro idioma (`spoken`, em `lang`).
    """

    start: int  # posição no texto exibido (idioma base), em caracteres
    end: int  # fim exclusivo
    text: str  # o trecho original, no idioma base
    spoken: str  # o que é falado no lugar dele, no outro idioma
    lang: str  # idioma do trecho falado: "en-US" ou "pt-BR"
    annotation_id: int


@dataclass(frozen=True)
class ComposedText:
    ssml: str  # <speak> com <lang> nos trechos trocados; vai ao TTS (sem <voice>: quem põe é o adaptador)
    text: str  # o texto exibido, no idioma base, sem nenhuma marcação
    swaps: list[Swap]  # em ordem de posição


@dataclass(frozen=True)
class SentenceDensity:
    """Densidade de uma frase (perfil devolvido pela prévia, US11)."""

    segment_id: int
    position: int
    candidates: int  # trechos da frase que podem ser trocados
    swapped: int  # trechos de fato trocados no SSML da frase
    target: float  # fração-alvo de trocas nesta altura da história (0 a 1): a curva, ou a densidade fixa
