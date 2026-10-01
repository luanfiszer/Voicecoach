/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_GOOGLE_WEB_CLIENT_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Injetada pelo `define` do `vite.config.ts`: a versão do `package.json`. */
declare const __VERSAO_DA_WEB__: string;
