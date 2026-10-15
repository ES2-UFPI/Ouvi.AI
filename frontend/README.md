# React + TypeScript + Vite

Este template fornece uma configuração mínima para colocar o React a funcionar no Vite com HMR e algumas regras do Oxlint.

Atualmente, estão disponíveis dois plugins oficiais:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) utiliza o [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) utiliza o [SWC](https://swc.rs/)

## Passo a Passo de Setup

Para garantir que a equipa consegue iniciar o projeto sem problemas, segue os passos de configuração abaixo[cite: 5]:

1. **Clonar o repositório** para a tua máquina local[cite: 5].
2. **Copiar o ficheiro `.env.example` para `.env`** para configurar as variáveis de ambiente[cite: 5].
3. **Executar `docker compose up -d`** na raiz do projeto para iniciar os serviços em segundo plano[cite: 5].
4. **Instalar as dependências do frontend**[cite: 5] utilizando o teu gestor de pacotes preferido (por exemplo, `npm install`, `yarn install` ou `pnpm install`).

## React Compiler

O React Compiler não está ativado neste template devido ao seu impacto no desempenho durante o desenvolvimento e a compilação (build). Para o adicionares, consulta [esta documentação](https://react.dev/learn/react-compiler/installation).

## Expandir a configuração do Oxlint

Se estiveres a desenvolver uma aplicação para produção, recomendamos a ativação das regras de lint baseadas em tipos. Para isso, instala o `oxlint-tsgolint` e edita o ficheiro `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}