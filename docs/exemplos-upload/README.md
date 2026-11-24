# Exemplos para "Enviar sua história" (US18)

Três fábulas de Esopo em inglês (domínio público, edição do Project Gutenberg, ebook #21), com tradução e glossário
feitos pela equipe. Na tela inicial, em **Enviar sua história**, escolha um destes arquivos e clique em **Enviar**.

| Arquivo | Formato | Melhor filtro para ouvir |
|---|---|---|
| `the_fox_and_the_crow.txt` | `.txt` | English → Palavras difíceis → Intermediário → Alta (7 trocas) |
| `the_lion_and_the_mouse.txt` | `.txt` | English → Palavras difíceis → Intermediário → Alta (6 trocas) |
| `the_north_wind_and_the_sun.json` | `.json` | English → Palavras difíceis → Intermediário → Alta (5 trocas) |

## Formato do `.txt`

```text
# Título (opcional)

Frase em inglês.
Tradução em português.

= termo em inglês -> como ele aparece no português
```

As linhas `=` formam o **glossário**: dizem qual trecho do português corresponde a cada termo do inglês. Sem elas, só
são trocadas as palavras que o dicionário do catálogo já conhece. Várias formas podem ser separadas por `|`.

## Formato do `.json`

O mesmo das histórias do catálogo (`backend/app/modules/stories/seed/`): `title`, `description` e `segments` com `en` e
`pt`, mais o campo opcional `glossary` (`{"termo": "tradução"}`).

Limites: 100 KB, 60 frases e 500 caracteres por frase.
