# Origem e licença dos textos

| Arquivo | História | Origem | Licença |
|---|---|---|---|
| `a_raposa_e_as_uvas.json` | A Raposa e as Uvas | Fábula de Esopo | Domínio público |
| `a_lebre_e_a_tartaruga.json` | A Lebre e a Tartaruga | Fábula de Esopo | Domínio público |
| `o_patinho_feio.json` | O Patinho Feio | Conto de Hans Christian Andersen (1843) | Domínio público |

As histórias originais são de domínio público. Os textos deste diretório, em inglês e em português,
são **recontagens originais**, escritas para o projeto: não reproduzem nenhuma tradução publicada
específica, para não carregar direitos de tradução de terceiros.

## Critérios usados na escrita

- Cada frase tem, no máximo, 200 caracteres, para facilitar a geração de áudio frase a frase.
- Cada história tem pelo menos 6 phrasal verbs distintos em inglês, e pelo menos 2 deles separáveis
  (por exemplo, *bring them down*, em que o objeto fica entre o verbo e a partícula).
- Cada phrasal verb tem um equivalente natural na frase em português, para o alinhamento dos trechos
  (e a troca de idioma no áudio) funcionar.
- Algumas frases não têm phrasal verb, e algumas têm "armadilhas" (verbo seguido de preposição, como
  *walking through*), para testar o detector sem favorecê-lo.

## O campo `phrasal_verbs`

Dentro de cada frase, `phrasal_verbs` lista os phrasal verbs que o autor sabe que estão ali, com o trecho
exato em inglês (`en`), o equivalente em português (`pt`) e se é separável. **Esses dados não vão para o
banco**: servem para conferir o conteúdo (veja `tests/test_seed_integrity.py`) e como referência para o
detector e o alinhamento das próximas etapas.
